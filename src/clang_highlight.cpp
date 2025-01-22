// clang-highlight produces semantic highlighting information
// Author: Max Schwarz <max.schwarz@online.de>

#include <clang/Basic/Specifiers.h>
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wnonnull"
#include <clang/AST/NestedNameSpecifier.h>
#include <clang/AST/TypeLoc.h>
#include <clang/ASTMatchers/ASTMatchFinder.h>
#include <clang/ASTMatchers/ASTMatchers.h>
#include <clang/Basic/SourceLocation.h>
#include <clang/Basic/TokenKinds.h>
#include <clang/Frontend/FrontendActions.h>
#include <clang/Lex/Lexer.h>
#include <clang/Tooling/ArgumentsAdjusters.h>
#include <clang/Tooling/CommonOptionsParser.h>
#include <clang/Tooling/Tooling.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Support/JSON.h>
#include <llvm/Support/raw_os_ostream.h>
#pragma GCC diagnostic pop

#include <fstream>
#include <iostream>

using namespace clang;
using namespace clang::ast_matchers;
using namespace clang::tooling;
using namespace llvm;

static constexpr bool LINK_DUMP = false;

struct Link {
  std::string name;
  std::string qualifiedName;
  std::vector<std::string> parameterTypes;
  std::string dump;
  StringRef file;
  unsigned int line;
  unsigned int column;
};

struct ResultToken {
  enum class Type {
    Whitespace,
    Keyword,
    Name,
    StringLiteral,
    NumberLiteral,
    OtherLiteral,
    Operator,
    Punctuation,
    Comment,
    Preprocessor,
    Variable,
    Other
  };

  static const char *typeName(Type type) {
    switch (type) {
    case Type::Whitespace:
      return "whitespace";
    case Type::Keyword:
      return "keyword";
    case Type::Name:
      return "name";
    case Type::StringLiteral:
      return "string_literal";
    case Type::NumberLiteral:
      return "number_literal";
    case Type::OtherLiteral:
      return "other_literal";
    case Type::Operator:
      return "operator";
    case Type::Punctuation:
      return "punctuation";
    case Type::Comment:
      return "comment";
    case Type::Preprocessor:
      return "preprocessor";
    case Type::Variable:
      return "variable";
    case Type::Other:
      return "other";
    }
    return "unknown";
  }
  static const char *typeCSS(Type type) {
    switch (type) {
    case Type::Whitespace:
      return nullptr;
    case Type::Keyword:
      return "k";
    case Type::Name:
      return "n";
    case Type::StringLiteral:
      return "s";
    case Type::NumberLiteral:
      return "m";
    case Type::OtherLiteral:
      return "l";
    case Type::Operator:
      return "o";
    case Type::Punctuation:
      return "p";
    case Type::Comment:
      return "c";
    case Type::Preprocessor:
      return "cp";
    case Type::Variable:
      return "nv";
    case Type::Other:
      return nullptr;
    }
    return nullptr;
  }

  void determineType(const clang::Preprocessor &pp) {
    type = [&]() {
      if (token.isLiteral()) {
        switch (token.getKind()) {
        case tok::numeric_constant:
          return Type::NumberLiteral;
        case tok::string_literal:
        case tok::utf8_string_literal:
        case tok::utf16_string_literal:
        case tok::utf32_string_literal:
        case tok::wide_string_literal:
          return Type::StringLiteral;
        default:
          return Type::OtherLiteral;
        }
      } else if (token.is(tok::raw_identifier)) {
        pp.LookUpIdentifierInfo(token);

        if (token.is(tok::identifier))
          return Type::Name;
        else
          return Type::Keyword;
      } else if (token.is(tok::comment))
        return Type::Comment;
      else
        return Type::Punctuation; // FIXME: What about Operators?
    }();
  }

  void addLink(const NamedDecl *decl, SourceManager &sourceManager,
               const clang::LangOptions &langOpts) {
    auto declLoc = decl->getLocation();

    link = Link{.name = decl->getNameAsString(),
                .qualifiedName = decl->getQualifiedNameAsString(),
                .file = sourceManager.getFilename(declLoc),
                .line = sourceManager.getSpellingLineNumber(declLoc),
                .column = sourceManager.getSpellingColumnNumber(declLoc)};

    if constexpr (LINK_DUMP) {
      llvm::raw_string_ostream dumpStream{link->dump};
      decl->dump(dumpStream);
    }

    if (auto func = dyn_cast<FunctionDecl>(decl)) {
      for (auto &param : func->parameters())
        link->parameterTypes.push_back(param->getType().getAsString(langOpts));
    }
  }

  ResultToken() = default;

  explicit ResultToken(const Token &token, const clang::Preprocessor &pp)
      : token{token} {
    determineType(pp);
  }

  explicit ResultToken(const Token &token, Type type)
      : token{token}, type{type} {}

  Token token;
  Type type = Type::Other;
  std::optional<Link> link;
};

static const NamedDecl *unspecialize(const NamedDecl *decl) {
  if (auto func = dyn_cast<FunctionDecl>(decl)) {
    if (auto instFrom = func->getInstantiatedFromMemberFunction())
      decl = instFrom;

    if (auto info = func->getTemplateSpecializationInfo()) {
      auto kind = info->getTemplateSpecializationKind();
      if (kind == clang::TSK_ImplicitInstantiation ||
          kind == clang::TSK_ExplicitInstantiationDeclaration) {
        if (auto instFrom =
                info->getTemplate()->getInstantiatedFromMemberTemplate()) {
          decl = instFrom->getTemplatedDecl();
        } else if (auto instFrom = info->getTemplate()) {
          decl = instFrom->getTemplatedDecl();
        }
      }
    }

    return decl;
  }

  if (auto redecl = dyn_cast<RedeclarableTemplateDecl>(decl)) {
    if (auto instFrom = redecl->getInstantiatedFromMemberTemplate())
      return instFrom->getTemplatedDecl();
    else
      return redecl->getTemplatedDecl();
  }

  return decl;
}

class TokenMap : public std::map<std::size_t, ResultToken> {
public:
  auto lowerBound(std::size_t offset) {
    return std::lower_bound(
        begin(), end(), offset,
        [](const auto &pair, std::size_t o) { return pair.first < o; });
  }
  auto lowerBound(std::size_t offset) const {
    return std::lower_bound(
        begin(), end(), offset,
        [](const auto &pair, std::size_t o) { return pair.first < o; });
  }

  ResultToken *getOrSplitToken(std::size_t offset) {
    auto it = lowerBound(offset);
    if (it == end())
      return {};

    if (it->first > offset) {
      // Are we inside the token before?
      --it;
      if (it == begin())
        return {}; // Nothing there

      std::size_t origLength = it->second.token.getLength();
      bool inside = it->first <= offset && it->first + origLength > offset;
      if (!inside)
        return {}; // Nothing there

      // Split token
      std::size_t firstOffset = it->first;
      ResultToken firstPart = it->second;

      std::size_t secondOffset = offset;
      ResultToken secondPart = it->second;

      firstPart.token.setLength(secondOffset - firstOffset);

      secondPart.token.setLocation(
          firstPart.token.getLocation().getLocWithOffset(
              firstPart.token.getLength()));
      secondPart.token.setLength(firstOffset + origLength - secondOffset);

      erase(it);
      emplace(firstOffset, std::move(firstPart));
      auto [itNew, _] = emplace(secondOffset, std::move(secondPart));

      return &itNew->second;
    } else if (it->first == offset) {
      return &it->second;
    } else
      throw std::logic_error{"getOrSplitToken logic error"};
  }
};

////////////////////////////////////////////////////////////////////////////////
// Semantic AST matchers

// Find references to declarations in expressions and link them
StatementMatcher DeclRefMatcher =
    declRefExpr(isExpansionInMainFile()).bind("declRefExpr");

class DeclRefExprHandler : public MatchFinder::MatchCallback {
public:
  explicit DeclRefExprHandler(TokenMap &tokens) : tokens{tokens} {}

  virtual void run(const MatchFinder::MatchResult &Result) {
    if (const auto *DRE =
            Result.Nodes.getNodeAs<clang::DeclRefExpr>("declRefExpr")) {

      auto &sourceManager = Result.Context->getSourceManager();
      auto loc = sourceManager.getSpellingLoc(DRE->getLocation());

      if (!loc.isValid() || !sourceManager.isWrittenInMainFile(loc))
        return;

      const NamedDecl *decl = DRE->getFoundDecl();
      if (!decl)
        return;

      decl = unspecialize(decl);

      auto offset = sourceManager.getFileOffset(loc);
      if (ResultToken *res = tokens.getOrSplitToken(offset)) {
        if (dyn_cast<VarDecl>(decl))
          res->type = ResultToken::Type::Variable;

        res->addLink(decl, sourceManager, Result.Context->getLangOpts());
      } else {
        std::cerr << "Looking for offset " << offset << "\n";
        DRE->dump();
        loc.dump(sourceManager);
        throw std::runtime_error{"Could not find DeclRefExpr token"};
      }
    }
  }

private:
  TokenMap &tokens;
};

// Find variable declarations and mark the tokens as variable names
DeclarationMatcher VarDeclMatcher =
    traverse(TK_IgnoreUnlessSpelledInSource,
             varDecl(isExpansionInMainFile()).bind("varDecl"));

class VarDeclHandler : public MatchFinder::MatchCallback {
public:
  explicit VarDeclHandler(TokenMap &tokens) : tokens{tokens} {}

  virtual void run(const MatchFinder::MatchResult &Result) {
    if (const auto *VD = Result.Nodes.getNodeAs<clang::VarDecl>("varDecl")) {

      auto &sourceManager = Result.Context->getSourceManager();
      auto loc = sourceManager.getSpellingLoc(VD->getLocation());

      if (!loc.isValid() || !sourceManager.isWrittenInMainFile(loc))
        return;

      auto offset = sourceManager.getFileOffset(loc);

      auto it = tokens.lowerBound(offset);
      if (it == tokens.end() || it->first != offset) {
        std::cerr << "Looking for offset " << offset << "\n";
        loc.dump(sourceManager);
        VD->dump();
        throw std::runtime_error{"Could not find VarDecl token"};
      }

      it->second.type = ResultToken::Type::Variable;
    }
  }

private:
  TokenMap &tokens;
};

// Find types and link them to their declarations
auto TypeMatcher =
    traverse(TK_IgnoreUnlessSpelledInSource, elaboratedTypeLoc().bind("loc"));

class TypeHandler : public MatchFinder::MatchCallback {
public:
  explicit TypeHandler(TokenMap &tokens) : tokens{tokens} {}

  virtual void run(const MatchFinder::MatchResult &Result) {
    if (const auto *N =
            Result.Nodes.getNodeAs<clang::ElaboratedTypeLoc>("loc")) {
      visitTypeLoc(Result.Context->getSourceManager(), *N);
    }
  }

private:
  void createLink(const SourceManager &sourceManager, SourceLocation fromLoc,
                  const NamedDecl *decl) {
    if (!decl)
      return;

    decl = unspecialize(decl);

    if (!decl)
      return;

    if (!sourceManager.isWrittenInMainFile(fromLoc))
      return;

    std::size_t fromOffset = sourceManager.getFileOffset(fromLoc);

    auto it = tokens.lowerBound(fromOffset);
    if (it == tokens.end())
      return;

    if (it->first != fromOffset)
      return;

    SourceLocation toLoc = decl->getLocation();

    it->second.link =
        Link{.name = decl->getNameAsString(),
             .qualifiedName = decl->getQualifiedNameAsString(),
             .file = sourceManager.getFilename(toLoc),
             .line = sourceManager.getSpellingLineNumber(toLoc),
             .column = sourceManager.getSpellingColumnNumber(toLoc)};
  }

  void visitTypeLoc(const SourceManager &sourceManager,
                    const ElaboratedTypeLoc &loc) {
    if (loc.isNull())
      return;

    auto inner = loc.getNextTypeLoc();
    if (inner.isNull())
      return;

    if (!sourceManager.isWrittenInMainFile(inner.getBeginLoc()))
      return;

    if (auto tloc = inner.getAs<TemplateSpecializationTypeLoc>()) {
      if (auto decl = tloc.getTypePtr()->getTemplateName().getAsTemplateDecl())
        createLink(sourceManager, tloc.getTemplateNameLoc(), decl);
    } else if (auto tloc = inner.getAs<TypedefTypeLoc>()) {
      createLink(sourceManager, tloc.getBeginLoc(),
                 tloc.getTypePtr()->getDecl());
    } else if (auto tloc = inner.getAs<UsingTypeLoc>()) {
      createLink(sourceManager, tloc.getBeginLoc(),
                 tloc.getTypePtr()->getFoundDecl());
    } else if (auto rloc = inner.getAs<RecordTypeLoc>()) {
      createLink(sourceManager, rloc.getBeginLoc(),
                 rloc.getTypePtr()->getDecl());
    }
  }

  TokenMap &tokens;
};

// Find references to members and link them
StatementMatcher MemberExprMatcher =
    memberExpr(isExpansionInMainFile()).bind("memberExpr");

class MemberExprHandler : public MatchFinder::MatchCallback {
public:
  explicit MemberExprHandler(TokenMap &tokens) : tokens{tokens} {}

  virtual void run(const MatchFinder::MatchResult &Result) {
    if (const MemberExpr *ME =
            Result.Nodes.getNodeAs<clang::MemberExpr>("memberExpr")) {

      auto &sourceManager = Result.Context->getSourceManager();
      auto loc = sourceManager.getSpellingLoc(ME->getMemberLoc());

      if (!loc.isValid() || !sourceManager.isWrittenInMainFile(loc))
        return;
      auto offset = sourceManager.getFileOffset(loc);

      auto it = tokens.lowerBound(offset);
      if (it == tokens.end() || it->first != offset)
        throw std::runtime_error{"Could not find MemberExpr token"};

      const NamedDecl *decl = ME->getMemberDecl();
      if (!decl)
        return;

      decl = unspecialize(decl);

      it->second.addLink(decl, sourceManager, Result.Context->getLangOpts());
    }
  }

private:
  TokenMap &tokens;
};

void dumpHTML(std::istream &in, std::ostream &out, const TokenMap &tokens) {
  out << R"EOS(<!doctype html>
            <html>
                <head>
                    <meta charset="UTF-8" />
                    <link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Source+Sans+Pro:400,400i,600,600i%7CSource+Code+Pro:400,400i,600&amp;subset=latin-ext" />
                    <link rel="stylesheet" href="https://static.magnum.graphics/m-dark.compiled.css" />
                    <link rel="stylesheet" href="https://static.magnum.graphics/m-dark.documentation.compiled.css" />
                    <style>
                        .m-code a {
                            color: inherit;
                            text-decoration: none;
                        }
                        .m-code a:hover {
                            text-decoration: underline;
                        }
                    </style>
                </head>
                <body>
                    <pre class="m-code">
)EOS";

  std::size_t textOffset = 0;
  std::vector<char> copyBuf;

  auto transfer = [&](std::size_t n) {
    copyBuf.resize(n);

    in.read(copyBuf.data(), n);

    for (char c : copyBuf) {
      switch (c) {
      case '&':
        out << "&amp;";
        break;
      case '<':
        out << "&lt;";
        break;
      case '>':
        out << "&gt;";
        break;
      case '"':
        out << "&quot;";
        break;
      case '\'':
        out << "&#39;";
        break;
      case '/':
        out << "&#47;";
        break;
      default:
        out << c;
        break;
      }
    }

    textOffset += n;
  };

  for (auto &[offset, token] : tokens) {
    if (offset > textOffset)
      transfer(offset - textOffset);

    const char *css = ResultToken::typeCSS(token.type);

    if (css)
      out << "<span class=\"" << css << "\">";

    if (token.link)
      out << "<a href=\"file://" << token.link->file.data() << "#"
          << token.link->line << "_" << token.link->name << "\">";

    transfer(token.token.getLength());

    if (token.link)
      out << "</a>";

    if (css)
      out << "</span>";
  }

  out << "</pre></body></html>\n";
}

enum class PunctuationMode { Keep, KeepLinked, Skip };

void dumpJSON(std::ostream &out, const std::string &file,
              const TokenMap &tokens,
              PunctuationMode punct = PunctuationMode::Keep) {
  {
    llvm::raw_os_ostream osOStream{out};
    llvm::json::OStream stream{osOStream, 2};

    stream.object([&]() {
      stream.attribute("file", file);
      stream.attributeArray("tokens", [&]() {
        for (const auto &[offset, token] : tokens) {
          if (token.type == ResultToken::Type::Punctuation) {
            if (punct == PunctuationMode::KeepLinked && !token.link)
              continue;
            if (punct == PunctuationMode::Skip)
              continue;
          }

          stream.object([&]() {
            stream.attribute("offset", offset);
            stream.attribute("length", token.token.getLength());
            stream.attribute("type", ResultToken::typeName(token.type));

            if (token.link) {
              stream.attributeObject("link", [&]() {
                stream.attribute("file", token.link->file);
                stream.attribute("line", token.link->line);
                stream.attribute("column", token.link->column);
                stream.attribute("name", token.link->name);
                stream.attribute("qualified_name", token.link->qualifiedName);

                if constexpr (LINK_DUMP)
                  stream.attribute("dump", token.link->dump);

                if (!token.link->parameterTypes.empty()) {
                  stream.attributeArray("parameter_types", [&]() {
                    for (auto &param : token.link->parameterTypes)
                      stream.value(param);
                  });
                }
              });
            }
          });
        }
      });
    });
  }
  out << "\n";
}

// Apply a custom category to all command-line options so that they are the
// only ones displayed.
static llvm::cl::OptionCategory MyCategory("clang_highlight options");

// CommonOptionsParser declares HelpMessage with a description of the common
// command-line options related to the compilation database and input files.
// It's nice to have this help message in all tools.
static cl::extrahelp CommonHelp(CommonOptionsParser::HelpMessage);

static cl::list<std::string> OptHTMLOut{"html-out",
                                        cl::desc{"Write HTML output to"},
                                        cl::value_desc{"out.html"},
                                        cl::cat{MyCategory},
                                        cl::Optional,
                                        cl::ValueOptional};
static cl::list<std::string> OptJSONOut{"json-out",
                                        cl::desc{"Write JSON output to"},
                                        cl::value_desc{"out.json"},
                                        cl::cat{MyCategory},
                                        cl::Optional,
                                        cl::ValueOptional};

static cl::opt<PunctuationMode> OptPunctMode{
    "punctuation", cl::desc{"Choose which punctuation tokens to keep"},
    cl::values(
        clEnumValN(PunctuationMode::Keep, "keep",
                   "Keep all punctuation (default)"),
        clEnumValN(
            PunctuationMode::KeepLinked, "linked",
            "Keep only punctuation tokens with links (e.g. custom operators)"),
        clEnumValN(PunctuationMode::Skip, "skip", "Skip all punctuation")),
    cl::init(PunctuationMode::Keep), cl::cat(MyCategory)};

// // A help message for this specific tool can be added afterwards.
// static cl::extrahelp MoreHelp("\nMore help text...\n");

int main(int argc, const char **argv) {
  cl::SetVersionPrinter([&](llvm::raw_ostream &stream) {
    stream << "clang-highlight version " << CH_VERSION_MAJOR << "."
           << CH_VERSION_MINOR << "." << CH_VERSION_PATCH << "\n";
  });

  auto ExpectedParser = CommonOptionsParser::create(
      argc, argv, MyCategory, cl::NumOccurrencesFlag::Required);
  if (!ExpectedParser) {
    // Fail gracefully for unsupported options.
    llvm::errs() << ExpectedParser.takeError();
    return 1;
  }
  CommonOptionsParser &OptionsParser = ExpectedParser.get();
  ClangTool Tool(OptionsParser.getCompilations(),
                 OptionsParser.getSourcePathList());

  // We need information about preprocessor operation to highlight
  // preprocessor directives and macro instantiations properly
  Tool.appendArgumentsAdjuster(
      getInsertArgumentAdjuster({"-Xclang", "-detailed-preprocessing-record"},
                                ArgumentInsertPosition::END));

  // Load additional clang flags from our config directory
  Tool.appendArgumentsAdjuster(
      getInsertArgumentAdjuster("--config-user-dir=~/.config/clang-highlight",
                                ArgumentInsertPosition::BEGIN));

  std::vector<std::unique_ptr<ASTUnit>> ASTs;
  if (auto ret = Tool.buildASTs(ASTs))
    return ret;

  auto &ast = ASTs.front();
  auto &sourceManager = ast->getSourceManager();

  // Lexing
  StringRef buffer = [&]() {
    bool invalid = false;
    buffer =
        sourceManager.getBufferData(sourceManager.getMainFileID(), &invalid);
    if (invalid) {
      std::cerr << "Could not get source text\n";
      std::exit(1);
    }

    return buffer;
  }();
  Lexer lexer(sourceManager.getLocForStartOfFile(sourceManager.getMainFileID()),
              ast->getLangOpts(), buffer.begin(), buffer.data(), buffer.end());
  lexer.SetCommentRetentionState(true);

  TokenMap tokens;

  Token tok;
  do {
    lexer.LexFromRawLexer(tok);
    if (tok.is(tok::eof))
      break;

    ResultToken res{tok, ast->getPreprocessor()};

    tokens[sourceManager.getFileOffset(tok.getLocation())] = res;
  } while (lexer.getBufferLocation() < buffer.end());

  // Handle preprocessor statements
  {
    auto &rec = *ast->getPreprocessor().getPreprocessingRecord();
    auto prepBegin = rec.local_begin();
    auto prepEnd = rec.local_end();

    for (auto it = prepBegin; it != prepEnd; ++it) {
      auto preproc = *it;
      auto beginLoc = preproc->getSourceRange().getBegin();
      if (!sourceManager.isWrittenInMainFile(beginLoc) ||
          ast->isInPreambleFileID(beginLoc) ||
          !rec.isEntityInFileID(it, sourceManager.getMainFileID()))
        continue;

      auto beginOffset =
          sourceManager.getFileOffset(preproc->getSourceRange().getBegin());
      auto tokenIt = tokens.lowerBound(beginOffset);

      if (tokenIt == tokens.end() || tokenIt->first != beginOffset) {
        std::cerr << "WARNING: Could not find token for offset " << beginOffset
                  << "\n";
        preproc->getSourceRange().dump(sourceManager);
        continue;
      }

      switch (preproc->getKind()) {
      case PreprocessedEntity::EntityKind::InclusionDirectiveKind: {
        // Mark entire range as preprocessor
        auto end = clang::Lexer::getLocForEndOfToken(
            preproc->getSourceRange().getEnd(), 0, sourceManager,
            ast->getLangOpts());
        auto endOffset = sourceManager.getFileOffset(end);

        clang::Token lexerToken = tokenIt->second.token;
        lexerToken.setLength(endOffset - beginOffset);

        while (tokenIt != tokens.end()) {
          if (tokenIt->first > endOffset)
            break;

          tokenIt = tokens.erase(tokenIt);
        }

        tokens[beginOffset] =
            ResultToken{lexerToken, ResultToken::Type::Preprocessor};
        break;
      }
      case PreprocessedEntity::EntityKind::MacroExpansionKind:
        // Mark only first token as preprocessor
        tokenIt->second.type = ResultToken::Type::Preprocessor;

        if (MacroExpansion *expansion = dyn_cast<MacroExpansion>(preproc)) {
          if (auto def = expansion->getDefinition()) {
            auto loc = def->getLocation();
            auto file = sourceManager.getFilename(loc);

            if (!sourceManager.isWrittenInMainFile(loc) && !file.empty()) {
              tokenIt->second.link =
                  Link{.name = def->getName()->getName().str(),
                       .qualifiedName = def->getName()->getName().str(),
                       .file = file,
                       .line = sourceManager.getSpellingLineNumber(loc),
                       .column = sourceManager.getSpellingColumnNumber(loc)};
            }
          }
        }

        break;
      default:
        break;
      }
    }
  }

  // Semantic AST pass
  DeclRefExprHandler declRefHandler{tokens};
  VarDeclHandler varDeclHandler{tokens};
  TypeHandler typeHandler{tokens};
  MemberExprHandler memberHandler{tokens};
  MatchFinder Finder;
  Finder.addMatcher(DeclRefMatcher, &declRefHandler);
  Finder.addMatcher(VarDeclMatcher, &varDeclHandler);
  Finder.addMatcher(::TypeMatcher, &typeHandler);
  Finder.addMatcher(MemberExprMatcher, &memberHandler);
  Finder.matchAST(ast->getASTContext());

  // Dump HTML
  if (!OptHTMLOut.empty()) {
    std::ifstream in{ast->getMainFileName().data()};

    if (OptHTMLOut.front().empty())
      dumpHTML(in, std::cout, tokens);
    else {
      std::ofstream out{OptHTMLOut.front()};
      dumpHTML(in, out, tokens);
    }
  }

  // Dump JSON
  if (!OptJSONOut.empty()) {
    std::ofstream out{OptJSONOut.front()};
    auto file = ast->getMainFileName().str();

    if (OptJSONOut.front().empty())
      dumpJSON(std::cout, file, tokens, OptPunctMode);
    else {
      std::ofstream out{OptJSONOut.front()};
      dumpJSON(out, file, tokens, OptPunctMode);
    }
  }

  return 0;
}

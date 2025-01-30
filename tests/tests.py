import unittest
import clang_highlight
from typing import Tuple, Optional
from clang_highlight import TokenType, Token, HighlightedCode


class CHTests(unittest.TestCase):
    def run_ch(self, code: str) -> HighlightedCode:
        h = clang_highlight.run(code=code)
        self.assertEqual(len(h.diagnostics), 0, f"Diagnostics:\n{h.diagnostics}")

        return h

    def get_token(
        self, highlighted: clang_highlight.HighlightedCode, fragment: str
    ) -> Tuple[str, Optional[Token]]:
        offset = highlighted.code.index(fragment.encode("utf8"))

        for text, token in highlighted:
            if token and token.offset == offset:
                return text, token

        return None, None

    def test_simple(self):
        code = """
        #include <iostream>
        int main(int argc, char** argv)
        {
            std::cout << "Hello World!\\n";
            return 0;
        }
        """

        h = self.run_ch(code)

        _, tok_include = self.get_token(h, "#include")
        self.assertEqual(tok_include.type, TokenType.PREPROCESSOR)

        _, tok_cout = self.get_token(h, "cout")
        self.assertEqual(tok_cout.type, TokenType.VARIABLE)
        self.assertTrue(tok_cout.link)
        self.assertEqual(tok_cout.link.qualified_name, "std::cout")

    def test_template_inst(self):
        code = """
        #include <vector>

        int main(int argc, char** argv)
        {
            auto myLambda = [](auto& obj){
                obj.emplace_back();
            };

            std::vector<int> v;
            myLambda(v);
        }
        """

        h = self.run_ch(code)

        _, tok_help = self.get_token(h, "emplace_back();")
        self.assertEqual(tok_help.type, TokenType.NAME)
        self.assertEqual(tok_help.link.qualified_name, "std::vector::emplace_back")

    def test_unspecialize(self):
        code = """
        template<class T>
        class Test
        {
        public:
            void test(int a, bool b)
            {}

            template<class K>
            void func_template(int a, bool b)
            {}

            template<>
            void func_template<int>(int a, bool b)
            {}

            template<class K>
            using Type = Test<K>;
        };

        using Type2 = bool;

        template<class T>
        void func(T)
        {}

        int main(int argc, char** argv)
        {
            Test<int> instance;
            instance.test(0, true);
            instance.func_template<bool>(0, true);
            instance.func_template<int>(0, true);

            Test<int>::Type<bool> other [[maybe_unused]];

            Type2 other2 [[maybe_unused]];

            func(0);
        }
        """

        h = self.run_ch(code)

        _, tok_test = self.get_token(h, "test(0, true);")
        self.assertEqual(tok_test.link.qualified_name, "Test::test")
        self.assertEqual(tok_test.link.parameter_types, ["int", "bool"])

        _, tok_test = self.get_token(h, "func_template<bool>(0, true);")
        self.assertEqual(tok_test.link.qualified_name, "Test::func_template")
        self.assertEqual(tok_test.link.parameter_types, ["int", "bool"])
        self.assertEqual(tok_test.link.line, 10)

        _, tok_test = self.get_token(h, "func_template<int>(0, true);")
        self.assertEqual(tok_test.link.qualified_name, "Test::func_template")
        self.assertEqual(tok_test.link.parameter_types, ["int", "bool"])
        self.assertEqual(tok_test.link.line, 14)

        _, tok_type = self.get_token(h, "Type<bool>")
        self.assertEqual(tok_type.link.qualified_name, "Test::Type")

        _, tok_type = self.get_token(h, "Type2 other2")
        self.assertEqual(tok_type.link.qualified_name, "Type2")

        _, tok_call = self.get_token(h, "func(0);")
        self.assertEqual(tok_call.link.qualified_name, "func")
        self.assertEqual(tok_call.link.parameter_types, ["T"])

    def test_preprocessor(self):
        code = """
        #include <iostream>
        # include <cmath>
        #include"cstdlib"
        """

        h = self.run_ch(code)

        _, tok = self.get_token(h, "#include <iostream>")
        self.assertEqual(tok.type, TokenType.PREPROCESSOR)

        _, tok = self.get_token(h, "<iostream>")
        self.assertEqual(tok.type, TokenType.PREPROCESSOR_FILE)

    def test_strings(self):
        code = r"""
        const char* str1 = "newline: \n";
        const char* str2 = "\U0001F600";
        const char* str3 = "{} {a}";
        """

        h = self.run_ch(code)

        text, tok = self.get_token(h, r"\n")
        self.assertEqual(tok.type, TokenType.STRING_LITERAL_ESCAPE)
        self.assertEqual(text, r"\n")

        text, tok = self.get_token(h, r"\U0001F600")
        self.assertEqual(tok.type, TokenType.STRING_LITERAL_ESCAPE)
        self.assertEqual(text, r"\U0001F600")

        text, tok = self.get_token(h, r"{}")
        self.assertEqual(tok.type, TokenType.STRING_LITERAL_INTERPOLATION)
        self.assertEqual(text, r"{}")

        text, tok = self.get_token(h, r"{a}")
        self.assertEqual(tok.type, TokenType.STRING_LITERAL_INTERPOLATION)
        self.assertEqual(text, r"{a}")

    def test_include(self):
        code = r"""
        #include <iostream>
        """

        h = self.run_ch(code)

        text, tok = self.get_token(h, r"#include")
        self.assertEqual(tok.type, TokenType.PREPROCESSOR)
        self.assertTrue(tok.link is None)

        text, tok = self.get_token(h, r"<iostream>")
        self.assertEqual(tok.type, TokenType.PREPROCESSOR_FILE)
        self.assertTrue(tok.link is not None)
        self.assertEqual(tok.link.name, "<file>")
        self.assertEqual(tok.link.file.name, "iostream")
        self.assertTrue(tok.link.file.is_absolute())


if __name__ == "__main__":
    unittest.main()

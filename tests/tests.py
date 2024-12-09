import unittest
import subprocess
import json
import tempfile
from pathlib import Path


class CHTests(unittest.TestCase):

    def run_ch(self, code: bytes):
        with tempfile.TemporaryDirectory(delete=False) as build_dir:
            build_dir = Path(build_dir)
            code_path = build_dir / 'code.cpp'
            with open(code_path, 'wb') as code_file:
                code_file.write(code)

            with open(build_dir / 'compile_commands.json', 'w') as db_file:
                db_file.write(
                    json.dumps([{
                        'directory': str(build_dir),
                        'command':
                        f'/usr/bin/c++ -DNDEBUG -std=c++20 -Wall {code_path}',
                        'file': str(code_path),
                    }]))

            result = subprocess.run(
                ['clang-highlight', '-p', build_dir, '--json-out', code_path],
                stdout=subprocess.PIPE)

        self.assertEqual(result.returncode, 0)

        data = json.loads(result.stdout.decode('utf8'))

        self.assertEqual(data['file'], str(code_path))
        self.validate_tokens(data['tokens'], code)

        return data['tokens']

    def validate_tokens(self, tokens: list, code: bytes):
        code_offset = 0

        for token in tokens:
            self.assertIn('type', token)

            off = token['offset']
            length = token['length']
            self.assertGreaterEqual(off, code_offset)
            self.assertGreater(length, 0)

            # All intermediate is whitespace
            if off > code_offset:
                self.assertTrue(code[code_offset:off].isspace())

            code_offset = off + length

    def get_token(self, code: bytes, tokens: list, fragment: bytes):
        offset = code.index(fragment)
        matching = [tok for tok in tokens if tok['offset'] == offset]
        self.assertEqual(len(matching), 1)

        return matching[0]

    def test_simple(self):
        code = """
        #include <iostream>
        int main(int argc, char** argv)
        {
            std::cout << "Hello World!\\n";
            return 0;
        }
        """.encode('utf8')

        tokens = self.run_ch(code)

        tok_include = self.get_token(code, tokens, b'#include')
        self.assertEqual(tok_include['type'], "preprocessor")

        tok_cout = self.get_token(code, tokens, b'cout')
        self.assertEqual(tok_cout['type'], 'variable')
        self.assertIn('link', tok_cout)
        self.assertEqual(tok_cout['link']['qualified_name'], 'std::cout')

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
        """.encode('utf8')

        tokens = self.run_ch(code)

        tok_help = self.get_token(code, tokens, b'emplace_back();')
        self.assertEqual(tok_help['type'], 'name')
        self.assertEqual(tok_help['link']['qualified_name'],
                         'std::vector<int>::emplace_back')


if __name__ == "__main__":
    unittest.main()

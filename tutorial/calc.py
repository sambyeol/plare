import argparse
from plare import build_grammar
from plare import build_lang
from plare import Lexer
from plare import Parser
from plare import Rule
from plare import Token
from plare import Type

# define language
# num -> n
# exp -> num
#      | exp + exp
#      | exp - exp
#      | exp * exp
#      | exp / exp
num = Type('num', alias=int)
exp = Type('exp',
  Const=[num],
  Add=['exp', 'exp'],
  Sub=['exp', 'exp'],
  Mul=['exp', 'exp'],
  Div=['exp', 'exp'])
num, exp = build_lang(num, exp)

# define tokens
TOKENS = {
  Token('CONST', int): r'-?(0|[1-9][0-9]*)',
  Token('PLUS'): r'\+',
  Token('MINUS'): r'-',
  Token('STAR'): r'\*',
  Token('SLASH'): r'/',
  Token('LPAREN'): r'\(',
  Token('RPAREN'): r'\)',
}
IGNORES = {
  Token('WHITESPACE'): r'[ \t\n]+',
  Token('COMMENT'): r'//.*//',
}

# make lexer
lexer = Lexer(TOKENS, ignore=IGNORES)
TOKENS = lexer.TOKENS

# define grammar
# P: E -> $1
# E: N -> E.Const($1)
#  | ( E ) -> $2
#  | E + E -> exp.Add($1, $3)
#  | E - E -> exp.Sub($1, $3)
#  | E * E -> exp.Mul($1, $3)
#  | E / E -> exp.Div($1, $3)
# N: CONST -> num($1)
P = Rule('P', 
  (['E'], None, ['$1']))
E = Rule('E',
  (['N'], exp.Const, ['$1']),
  ([TOKENS.LPAREN, 'E', TOKENS.RPAREN], None, ['$2']),
  (['E', TOKENS.PLUS, 'E'], exp.Add, ['$1', '$3']),
  (['E', TOKENS.MINUS, 'E'], exp.Sub, ['$1', '$3']),
  (['E', TOKENS.STAR, 'E'], exp.Mul, ['$1', '$3']),
  (['E', TOKENS.SLASH, 'E'], exp.Div, ['$1', '$3']))
N = Rule('N',
  ([TOKENS.CONST], num, ['$1']))
P, E, N = build_grammar(P, E, N)

# make parser
parser = Parser(lexer, [P, E, N], P, precedence={TOKENS.STAR: 1, TOKENS.SLASH: 1})

# define interpretation function
def interprete(tree):
  if tree.data == 'Const':
    return tree.children[0]
  elif tree.data == 'Add':
    return interprete(tree.children[0]) + interprete(tree.children[1])
  elif tree.data == 'Sub':
    return interprete(tree.children[0]) - interprete(tree.children[1])
  elif tree.data == 'Mul':
    return interprete(tree.children[0]) * interprete(tree.children[1])
  else: # tree.data == 'Div'
    return interprete(tree.children[0]) // interprete(tree.children[1])

def main(args):

  print('This is a tutorial integer calculation project with plare')

  for calc_file in args.file:
    print()

    # read file
    if not calc_file.endswith('.calc'):
      raise Exception('File extension is not ".calc". Please check the argument "{}".'.format(calc_file))
    with open(calc_file) as f:
      src = f.read()
    print('== {} =='.format(calc_file))
    print(src)
    print('=' * (len(calc_file) + 6))

    # parse the source into ast
    tree = parser.parse(src)

    # interprete the ast
    result = interprete(tree)
    print('answer: {}'.format(result))
    print('=' * (len(calc_file) + 6))

if __name__ == '__main__':
  arg_parser = argparse.ArgumentParser('Integer calculator with plare')
  arg_parser.add_argument('file', metavar='*.calc', type=str, nargs='+', help='File that have integer arithmetic expressions')
  args = arg_parser.parse_args()
  main(args)

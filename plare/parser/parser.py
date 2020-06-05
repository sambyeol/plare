from itertools import cycle

from plare.lexer.token import Token
from plare.lexer.lexer import EOF
from plare.lexer.lexer import EPSILON
from plare.parser.automata import Edge
from plare.parser.automata import EdgeSet
from plare.parser.automata import State
from plare.parser.automata import StateSet
from plare.parser.exception import ReduceReduceConflict
from plare.parser.exception import ShiftReduceConflict
from plare.parser.rule import ARule
from plare.parser.rule import ARuleSet
from plare.parser.rule import Constructor
from plare.parser.rule import Rule
from plare.parser.table import Table

class Parser:
  
  __slots__ = ['__lexer', '__all_rules', '__table']

  def __init__(self, lexer, grammar, start, verbose=False, precedence=None, right_associative=None):
    self.__lexer = lexer

    precedence = {t: precedence[t] if t in precedence.keys() else 0 for t in self.__lexer.TOKENS.to_list()}
    right_associative = right_associative if type(right_associative) == list else [right_associative] if right_associative else []

    self.__all_rules = ARuleSet(grammar)

    def first(string):
      first_set = []
      string = iter(string)
      look_next = True
      while look_next:
        try:
          s = next(string)
        except StopIteration:
          break

        if isinstance(s, Token):
          if s == EPSILON:
            continue
          first_set.append(s)
          look_next = False

        elif isinstance(s, Rule):
          first_set.extend(s.first)
          if EPSILON not in s.first:
            look_next = False
        
        else:
          raise TypeError('[Error] Parser first: Unknown symbol {} is given.'.format(s))
      return first_set

    def lookahead(string, parent_ahead):
      lookahead_set = []
      for t in parent_ahead:
        first_set = first(string + [t])
        for t in first_set:
          if t not in lookahead_set:
            lookahead_set.append(t)
      return lookahead_set

    def closure(I):
      worklist = list(I)
      while len(worklist) > 0:
        r = worklist.pop(0)
        B = r.next_variable
        I_ = self.__all_rules.startswith(B)
        lookahead_set = lookahead(r.remain, r.lookahead)
        I_ = [arule.add_lookahead(lookahead_set) for arule in I_]
        if len(I_) > 0:
          I, updated = I.union(I_)
          worklist.extend(updated)
      return I

    def goto(I, X):
      J = State()
      for i in I:
        j = i.next(X)
        if j:
          J.add(j)
      return closure(J)

    if verbose:
      windmill = cycle('|||///---\\\\\\')
    start_rule = ARule('__start__', [start], None).add_lookahead([EOF])
    T = StateSet([closure(State([start_rule]))])
    worklist = list(T)
    E = EdgeSet()
    while len(worklist) > 0:
      if verbose:
        print('\rMaking parser...{}'.format(next(windmill)), end='')
      I = worklist.pop(0)
      for X in I.next_variables:
        J = goto(I, X)
        T, J, updated = T.add(J, return_updated=True)
        E = E.add(Edge(I, J, X))
        if updated:
          worklist.append(J)

    def precedence_of_rule(x):
      for t in x.terminals:
        if precedence[t] > 0:
          return precedence[t]
      for t in x.terminals:
        if precedence[t] < 0:
          return precedence[t]
      return 0

    self.__table = Table(len(T), len(self.__lexer.TOKENS), len(grammar))
    for edge in E:
      if verbose:
        print('\rMaking parser...{}'.format(next(windmill)), end='')
      self.__table[edge.I.name, edge.X] = ('shift' if isinstance(edge.X, Token) else 'goto', edge.J.name)

    end_rule = start_rule.next(start)
    for I in T:
      if end_rule in I:
        self.__table[I.name, EOF] = ('accept', None)

    for I in T:
      for arule in I:
        if arule.is_ended and arule.n is not None:
          for Y in arule.lookahead:
            if verbose:
              print('\rMaking parser...{}'.format(next(windmill)), end='')
            try:
              self.__table[I.name, Y] = ('reduce', arule.n)
            except ShiftReduceConflict:
              p_r = precedence_of_rule(arule)
              p_y = precedence[Y]
              if p_r > p_y:
                self.__table.resolve_conflict(I.name, Y, ('reduce', arule.n))
              elif p_r < p_y:
                pass
              else:
                if Y not in right_associative:
                  self.__table.resolve_conflict(I.name, Y, ('reduce', arule.n))
            except ReduceReduceConflict:
              _arule = self.__all_rules[self.__table[I.name, Y][1]]
              p_o = precedence_of_rule(_arule)
              p_n = precedence_of_rule(arule)
              if p_o > p_n:
                pass
              elif p_o < p_n:
                self.__table.resolve_conflict(I.name, Y, ('reduce', arule.n))
              else:
                raise ReduceReduceConflict('[Parser] __init__: Cannot resolve conflict between two reduce rules.\n\t{}\n\t{}'.format(_arule, arule))
    if verbose:
      print('\rMaking parser...Done!')

  def parse(self, src):

    current_state = 's0'
    stack = [current_state]
    symbols = []
    accepted = False
    token = None
    tokens = self.__lexer.lex(src)

    while not accepted:

      if token is None:
        token = next(tokens)
      
      action, aux = self.__table[current_state, token]

      if action == 'shift':
        current_state = aux
        stack.append(current_state)
        symbols.append(token)
        token = None
      
      elif action == 'reduce':
        arule = self.__all_rules[aux]
        right = arule.right

        stack = stack[:-len(right)]
        current_state = stack[-1]
        
        poped = symbols[-len(right):]
        symbols = symbols[:-len(right)]
        symbol = arule.constructor(poped)
        
        _, current_state = self.__table[current_state, arule]
        stack.append(current_state)
        symbols.append(symbol)

      elif action == 'accept':
        accepted = True

    return symbols[-1]

from pypar.lexer.token import Token
from pypar.lexer.token import TokenObject
from pypar.parser.exception import ParsingTableError
from pypar.parser.exception import ReduceReduceConflict
from pypar.parser.exception import ShiftReduceConflict
from pypar.parser.exception import WrongAction
from pypar.parser.rule import ARule
from pypar.parser.rule import Rule

class Row:
  
  __slots__ = ['__state', '__n_token', '__n_variable', '__token_entries', '__rule_entries']

  def __init__(self, state, n_token, n_variable):
    self.__state = state
    self.__n_token = n_token
    self.__n_variable = n_variable
    self.__token_entries = {}
    self.__rule_entries = {}

  def __getitem__(self, variable):
    if isinstance(variable, Token) or isinstance(variable, TokenObject):
      return self.__token_entries[variable.id]
    elif isinstance(variable, Rule) or isinstance(variable, ARule):
      return self.__rule_entries[variable.left]
    else:
      raise TypeError('[Error] Row {}: Unknown variable type {} is given.'.format(self.__state, variable))

  def __setitem__(self, variable, action):
    if isinstance(variable, Token):
      if action[0] not in ['shift', 'reduce', 'accept']:
        raise WrongAction('[Error] Row {}: Action must be one of shift or reduce for token {}, but {} is given.'.format(self.__state, variable.id, action[0]))
      try:
        _action = self.__token_entries[variable.id]
        if _action[0] == 'shift' and action[0] == 'reduce':
          raise ShiftReduceConflict('[Conflict] Row {}: Conflict on token {}.'.format(self.__state, variable.id))
        elif _action[0] == 'reduce' and action[0] == 'reduce':
          raise ReduceReduceConflict('[Conflict] Row {}: Conflict on token {}.'.format(self.__state, variable.id))
        raise ParsingTableError('[Error] Row {}: Unknown parsing table error. The action for {} is already determined to {}, but new action {} is given'.format(self.__state, variable.id, _action[0], action[0]))
      except KeyError:
        pass
      self.__token_entries[variable.id] = action

    elif isinstance(variable, Rule):
      if action[0] != 'goto':
        raise WrongAction('[Error] Row {}: Action must be goto for varibable {}, but {} is given.'.format(self.__state, variable.left, action[0]))
      try:
        _action = self.__rule_entries[variable.left]
        raise ParsingTableError('[Error] Row {}: Unknown parsing table error. The action for {} is already determined to {}, but new action {} is given'.format(self.__state, variable.left, _action, action))
      except KeyError:
        pass
      self.__rule_entries[variable.left] = action
    else:
      raise TypeError('[Error] Row {}: Unsupported type of variable {} is given'.format(self.__state, variable))
    
  def resolve_conflict(self, variable, action):
    self.__token_entries[variable.id] = action

  def __repr__(self):
    r = self.__state + ' | '
    for t, a in self.__token_entries.items():
      r = r + str(t) + ': ({}, {})'.format(a[0], a[1] if a[0] == 'shift' else a[1]) + ' '
    for ru, a in self.__rule_entries.items():
      r = r + str(ru) + ': ({}, {})'.format(a[0], a[1]) + ' '
    return r

class Table:

  __slots__ = ['__n_state', '__n_token', '__n_variable', '__table']

  def __init__(self, n_state, n_token, n_variable):
    self.__n_state = n_state
    self.__n_token = n_token
    self.__n_variable = n_variable
    self.__table = {'s{}'.format(i): Row('s{}'.format(i), self.__n_token, self.__n_variable) for i in range(self.__n_state)}

  def __getitem__(self, tup):
    state, variable = tup
    return self.__table[state][variable]

  def __setitem__(self, tup, action):
    state, variable = tup
    self.__table[state][variable] = action

  def __repr__(self):
    return '\n'.join([str(r) for _, r in self.__table.items()])

  def resolve_conflict(self, state, variable, action):
    self.__table[state].resolve_conflict(variable, action)

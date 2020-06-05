from plare.lexer.lexer import EOF
from plare.lexer.lexer import EPSILON
from plare.lexer.token import Token
from plare.lexer.token import TokenObject

class Constructor:

  __slots__ = ['__const', '__args']

  def __init__(self, constructor, args):
    self.__const = constructor if constructor else (lambda *x: (x[0] if len(x) == 1 else x))
    self.__args = [int(i[1:]) - 1 if type(i) == str and i.startswith('$') else i for i in args]

  def __call__(self, xs):
    args = [(xs[i].value if isinstance(xs[i], TokenObject) else xs[i]) if type(i) == int else i for i in self.__args]
    return self.__const(*args)

class Rule:

  __slots__ = ['__name', '__rules', '__built', '__first_built', '__first']

  def __init__(self, name, *rules):
    self.__name = name
    self.__rules = list(rules)
    self.__built = False
    self.__first_built = False
    self.__first = []

  def build(self, rules):
    if self.__built:
      print('[Warning] Rule {}: This rule is already built.'.format(self.__name))
    rule_constructor = []
    for rule, constructor, args in self.__rules:
      rule = [rules[v] if type(v) == str else v for v in rule]
      constructor = Constructor(constructor, args)
      rule_constructor.append((rule, constructor))
    self.__rules = rule_constructor
    self.__built = True
    return self

  @property
  def name(self):
    return self.__name

  @property
  def left(self):
    return self.__name

  def get_arules(self):
    return [ARule(self.__name, r, c) for r, c in self.__rules]

  def __eq__(self, other):
    return self.__name == other.name if isinstance(other, Rule) else False

  def __repr__(self):
    return self.__name

  def build_first(self, rules):
    first_set = []
    if not self.__first_built:
      recursive_rules = []
      for rule, _ in self.__rules:
        recursion = False
        look_next = True
        first = []
        while look_next:
          iter_rule = iter(rule)
          try:
            s = next(iter_rule)
          except StopIteration:
            break

          if isinstance(s, Token):
            if s == EPSILON:
              continue
            first.append(s)
            look_next = False
          
          elif isinstance(s, Rule):
            if s == self:
              recursive_rules.append(rule)
              recursion = True
              break
            s = s.build_first(rules)
            first.extend(s.first)
            if EPSILON not in s.first:
              look_next = False
          
          else:
            raise TypeError('[Error] Rule {}: Unknown symbol {} is given.'.format(self.__name, s))
        
        if recursion:
          continue
        if len(first) == 0:
          first.append(EPSILON)
        first_set.extend(first)
      
      if EPSILON in first_set:
        for rule in recursive_rules:
          look_next = True
          first = []
          while look_next:
            iter_rule = iter(rule)
            try:
              s = next(iter_rule)
            except StopIteration:
              break

            if isinstance(s, Token):
              if s == EPSILON:
                continue
              first.append(s)
              look_next = False

            elif isinstance(s, Rule):
              if s == self:
                continue
              s = s.build_first(rules)
              first.extend(s.first)
              if EPSILON not in s.first:
                look_next = False
            
            else:
              raise TypeError('[Error] Rule {}: Unknown symbol {} is given.'.format(self.__name, s))
          
          first_set.extend(first)

      for s in first_set:
        if s not in self.__first:
          self.__first.append(s)
      self.__first_built = True
    return self

  @property
  def first(self):
    if not self.__first_built:
      print('[Warning] Rule {}: First is not built.'.format(self.__name))
    return self.__first

class ARule:

  __slots__ = ['__n', '__left', '__right', '__loc', '__constructor', '__lookahead']

  def __init__(self, left, right, constructor, loc=0, n=None):
    self.__n = n
    self.__left = left
    self.__right = right
    self.__loc = loc
    self.__constructor = constructor
    self.__lookahead = []

  def set_n(self, n):
    self.__n = n
    return self

  @property
  def left(self):
    return self.__left

  @property
  def right(self):
    return self.__right

  @property
  def constructor(self):
    return self.__constructor

  @property
  def next_variable(self):
    return self.__right[self.__loc] if self.__loc < len(self.__right) else None

  @property
  def loc(self):
    return self.__loc

  @property
  def n(self):
    return self.__n

  @property
  def lookahead(self):
    return self.__lookahead

  @property
  def remain(self):
    return self.__right[self.__loc + 1:]

  @property
  def terminals(self):
    return [s for s in self.__right if isinstance(s, Token)]

  def add_lookahead(self, lookaheads, return_update=False):
    updated = False
    for t in lookaheads:
      if t not in self.__lookahead:
        self.__lookahead.append(t)
        updated = True
    return (self, updated) if return_update else self

  def next(self, variable):
    return ARule(self.__left, self.__right, self.__constructor, loc=self.__loc + 1, n=self.__n).add_lookahead(self.__lookahead) if self.__loc < len(self.__right) and variable == self.__right[self.__loc] else None

  def __repr__(self):
    right = [str(v) for v in self.__right]
    return self.__left + ' -> ' + ' '.join(right[:self.__loc] + ['.'] + right[self.__loc:]) + ' | ' + str(self.__lookahead)

  def __eq__(self, other):
    if not isinstance(other, ARule):
      return False
    else:
      if self.__left != other.left:
        return False
      if self.__loc != other.loc:
        return False
      if len(self.__right) != len(other.right):
        return False
      for r_self, r_other in zip(self.__right, other.right):
        if r_self != r_other:
          return False
      return True

  @property
  def is_ended(self):
    return len(self.__right) <= self.__loc

class ARuleSet:

  __slots__ = ['__n', '__arules']

  def __init__(self, rules):
    self.__arules = []
    self.__n = 0
    for arule in sum([v.get_arules() for v in rules], []):
      if arule not in self.__arules:
        self.__arules.append(arule.set_n(self.__n))
        self.__n += 1

  def __len__(self):
    return self.__n

  def startswith(self, variable):
    rules = []
    for arule in self.__arules:
      if isinstance(variable, Rule) and arule.left == variable.name and arule not in rules:
        rules.append(ARule(arule.left, arule.right, arule.constructor, n=arule.n))
    return rules

  def __getitem__(self, idx):
    return self.__arules[idx]

  def find(self, arule):
    for i, rule in self.__arules:
      if arule == rule:
        return i
    raise AttributeError('[Error] ARules: Rule {} not found.'.format(arule))

  def __contains__(self, elem):
    return elem in self.__arules

def build(*rules):
  rules = {r.name: r for r in rules}
  rules = {k: r.build(rules) for k, r in rules.items()}
  rules = [r.build_first(rules) for _, r in rules.items()]
  return rules

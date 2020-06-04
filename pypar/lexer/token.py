from collections import namedtuple

TokenObject = namedtuple('TokenObject', ('id', 'value'))

class Token:
  
  __slots__ = ['id', 'type']

  def __init__(self, id, type=None):
    self.id = id.upper()
    self.type = type

  def __call__(self, value):
    if self.type:
      value = self.type(value)
    return TokenObject(self.id, value)

  def __hash__(self):
    return hash(self.id)

  def __eq__(self, other):
    return self.id == other.id if isinstance(other, Token) else False

  def __repr__(self):
    return self.id
  
  def __str__(self):
    return repr(self)
    
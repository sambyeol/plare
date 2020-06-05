import plare.lang.type

class Tree:

  __slots__ = ['__data', '__children']

  def __init__(self, data, children=None):
    self.__data = data
    self.__children = children if children is None or len(children) > 1 else children[0]

  @property
  def data(self):
    return self.__data

  def __repr__(self):
    return 'Tree(data={}{})'.format(self.__data, ', children=[{}]'.format(', '.join([str(e) for e in self.__children])) if self.__children else '')

class Constructor:

  __slots__ = ['__name', '__types']

  def __init__(self, name, types=None):
    self.__name = name
    self.__types = types

  def __call__(self, *values):

    if self.__types:
      if len(values) > len(self.__types):
        print('[Warning] Constructor {}: More than {} arguments are passed. Remaining part will be discarded'.format(self.__name, len(self.__types)))

      if len(values) < len(self.__types):
        raise TypeError('[Error] Constructor {}: Expecting {} arguments, but {} arguments are passed.'.format(self.__name, len(self.__types), len(values)))

      if values not in self:
        raise TypeError('[Error] Constructor {}: Type mismatch. Expecting ({}), but ({}) are given.'.format(self.__name, ', '.join([t.name if isinstance(t, plare.lang.type.Type) else t.__name__ for t, o in self.__types]), values))

      return Tree(self.__name, [values])

    else:
      if len(values) > 0:
        print('[Warning] Constructor {}: Arguments are passed to the singleton constructor.')
      return Tree(self.__name)

  def __repr__(self):
    return self.__name + (' of {}'.format(' * '.join([(t.name if isinstance(t, plare.lang.type.Type) else t.__name__) + (' list' if o == '*' else ' option' if o == '?' else '') for t, o in self.__types])) if self.__types else '')

  def __contains__(self, values):

    if (type(values) != list and type(values) != tuple) or (len(self.__types) == 1 and self.__types[0][1] == '*' and type(values[0]) != list):
      values = [values]
    
    for v, t_o in zip(values, self.__types):
      t, o = t_o

      if o == '?':
        if not (v is None or (v in t if isinstance(t, plare.lang.type.Type) else type(v) == t)):
          return False

      elif o == '*':
        if type(v) != list:
          return False
        for e in v:
          if not (e in t if isinstance(t, plare.lang.type.Type) else type(e) == t):
            return False

      else:
        if not (v in t if isinstance(t, plare.lang.type.Type) else type(v) == t):
          return False

    return True

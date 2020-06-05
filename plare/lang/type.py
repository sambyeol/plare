import plare.lang.tree

class Type:

  def __init__(self, name, alias=None, **kwargs):
    self.__name = name
    self.__built = False
    self.__alias = alias if alias is None or type(alias) == list else [alias]
    if self.__alias and len(kwargs) > 0:
      print('[Warning] Type {}: Other arguments will be discarded in alias mode'.format(self.__name))
    self.__dict = None if self.__alias else {k: t if t is None or type(t) == list else [t] for k, t in kwargs.items()}

  def __getattribute__(self, key):
    try:
      return super(Type, self).__getattribute__(key)
    except AttributeError:
      return self[key]

  def __getitem__(self, key):
    if not self.__built:
      print('[Warning] Type {}: This type is not built yet.'.format(self.__name))
    return self.__dict[key]

  @property
  def name(self):
    return self.__name

  @property
  def is_built(self):
    return self.__built

  def build(self, types):

    if self.__built:
      print('[Warning] Type {}: This type is already built.'.format(self.__name))

    if self.__alias:
      self.__alias = [(t[:-1], t[-1]) if type(t) == str and t[-1] in '?*' else (t, None) for t in self.__alias]
      self.__alias = [(types[t] if type(t) == str else t, o) for t, o in self.__alias]
    
    else:
      for k, ts in self.__dict.items():
        if ts is None:
          self.__dict[k] = plare.lang.tree.Constructor(k)
        else:
          ts = [(t[:-1], t[-1]) if type(t) == str and t[-1] in '?*' else (t, None) for t in ts]
          ts = [(types[t], o) if type(t) == str else (t, o) for t, o in ts]
          self.__dict[k] = plare.lang.tree.Constructor(k, ts)

    self.__built = True
    return self
  
  @property
  def is_alias(self):
    return True if self.__alias else False

  def __repr__(self):
    if self.__alias:
      return 'type {} = {}'.format(self.__name, ' * '.join([(t.name if isinstance(t, Type) else t.__name__) + (' list' if o == '*' else ' option' if o == '?' else '') for t, o in self.__alias]))
    else:
      return 'type {} =\n{}'.format(self.__name, '\n'.join(['  | {}'.format(c) for _, c in self.__dict.items()]))

  def __call__(self, *values):

    if not self.__built:
      print('[Warning] Type {}: This type is not build yet.'.format(self.__name))

    if self.__dict:
      raise TypeError('[Error] Type {}: Non-alias type cannot be a constructor.'.format(self.__name))

    if len(values) > len(self.__alias):
      raise TypeError('[Error] Type {}: This type takes at most {} arguments, but {} arguments are given.'.format(self.__name, len(self.__alias), len(values)))
    
    if values not in self:
      raise TypeError('[Error] Type {}: Type mismatch. Expecting "({})".'.format(self.__name, ', '.join([t.name if isinstance(t, Type) else t.__name__ for t, o in self.__alias])))

    return values[0] if len(values) == 1 else values

  def __contains__(self, elem):

    if self.__alias:
      if (type(elem) != list and type(elem) != tuple) or (len(self.__alias) == 1 and self.__alias[0][1] == '*' and elem[0] in self.__alias[0][0]):
        elem = [elem]
      for el, t_o in zip(elem, self.__alias):
        t, o = t_o

        if o == '?':
          if not (el is None or (el in t if isinstance(t, Type) else type(el) == t)):
            return False

        elif o == '*':
          if type(el) != list:
            return False
          for e in el:
            if not (e in t if isinstance(t, Type) else type(e) == t):
              return False

        else:
          if not (el in t if isinstance(t, Type) else type(el) == t):
            return False
      return True

    else:
      if isinstance(elem, plare.lang.tree.Tree):
        return elem.data in self.__dict.keys()

      else:
        return False

def build(*types):
  types = {t.name: t for t in types}
  types = {n: t.build(types) if t.is_alias else t for n, t in types.items()}
  types = {n: t.build(types) if not t.is_alias else t for n, t in types.items()}
  return [t for _, t in types.items()]

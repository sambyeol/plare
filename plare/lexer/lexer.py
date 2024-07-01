import re

from plare.lexer.exception import UnknownToken
from plare.lexer.token import Token

EOF = Token("EOF")
EPSILON = Token("EPSILON")


class Namespace:

    __slots__ = ["__keys", "__data"]

    def __init__(self, **kwargs):
        self.__keys = list(kwargs.keys())
        self.__data = dict(kwargs)

    def __repr__(self):
        return "Namespace({})".format(
            ", ".join(["{}={}".format(k, v) for k, v in self.data.items()])
        )

    def __getattribute__(self, key):
        try:
            return super(Namespace, self).__getattribute__(key)
        except AttributeError:
            return self.__data[key]

    def __getitem__(self, key):
        return self.__data[key]

    def __len__(self):
        return len(self.__keys)

    def to_list(self):
        return [t for _, t in self.__data.items()]


class Lexer:

    __slots__ = ["__token_regex", "__ignore_regex", "__comment_regex", "__TOKENS"]

    def __init__(self, tokens, ignore=None, comments=None):
        self.__token_regex = {t: re.compile(r) for t, r in tokens.items()}
        self.__ignore_regex = (
            {t: re.compile(r) for t, r in ignore.items()} if ignore else {}
        )
        self.__comment_regex = (
            [(re.compile(start), re.compile(end)) for start, end in comments]
            if comments
            else {}
        )
        self.__TOKENS = Namespace(**{t.id: t for t in tokens.keys()})

    @property
    def TOKENS(self):
        return self.__TOKENS

    def lex(self, src):

        while len(src) > 0:

            # check comments
            comment = False
            for start, end in self.__comment_regex:
                if start.match(src):
                    src = src[end.match(src).end() :]
                    comment = True
                    break
            if comment:
                continue

            # check ignores
            ignore = False
            for token, regex in self.__ignore_regex.items():
                if regex.match(src):
                    src = regex.sub("", src, 1)
                    ignore = True
                    break
            if ignore:
                continue

            # check tokens
            found = False
            for token, regex in self.__token_regex.items():
                match = regex.match(src)
                if match:
                    content = match.group()
                    src = regex.sub("", src, 1)
                    found = True
                    break
            if found:
                yield token(content)
                continue

            # if not matched to any of above
            raise UnknownToken("An unknown token is given: {}".format(src.split()[0]))

        yield EOF("")
        raise StopIteration("End of tokens")

from plare.parser.exception import DoublePointingEdge


class State:

    __slots__ = ["__name", "__arules"]

    def __init__(self, arules=None):
        self.__name = None
        self.__arules = arules if arules else []

    @property
    def next_variables(self):
        vars = []
        for r in self.__arules:
            if not r.is_ended and r.next_variable not in vars:
                vars.append(r.next_variable)
        return vars

    def union(self, other):
        update_set = []
        for rule in other:
            if rule in self.__arules:
                exist = self.find(rule)
                exist, updated = exist.add_lookahead(rule.lookahead, return_update=True)
                if updated:
                    update_set.append(exist)
            else:
                self.__arules.append(rule)
                update_set.append(rule)
        return self, update_set

    def find(self, arule):
        i = self.find_idx(arule)
        return self.__arules[i]

    def find_idx(self, arule):
        for i, r in enumerate(self.__arules):
            if arule == r:
                return i
        return None

    def __len__(self):
        return len(self.__arules)

    def __getitem__(self, idx):
        return self.__arules[idx]

    def add(self, arule):
        if arule not in self.__arules:
            self.__arules.append(arule)
        return self

    def __repr__(self):
        return "---{}---\n".format(self.__name) + "\n".join(
            [str(r) for r in self.__arules]
        )

    @property
    def name(self):
        return self.__name

    def set_name(self, name):
        self.__name = name
        return self

    def __eq__(self, other):
        for r_self, r_other in zip(self, other):
            if r_self != r_other:
                return False
        return True

    def __contains__(self, elem):
        return elem in self.__arules

    def merge(self, other, return_update=False):
        updated = False
        for arule in other:
            i = self.find_idx(arule)
            self.__arules[i], u = self.__arules[i].add_lookahead(
                arule.lookahead, return_update=True
            )
            updated = updated or u
        return (self, updated) if return_update else self


class StateSet:

    __slots__ = ["__states", "__n_state"]

    def __init__(self, states=None):
        self.__states = (
            [s.set_name("s{}".format(i)) for i, s in enumerate(states)]
            if states
            else []
        )
        self.__n_state = len(self.__states)

    def add(self, state, return_updated=False):
        i = self.find(state)
        updated = False
        if i < 0:
            state = state.set_name("s{}".format(self.__n_state))
            self.__states.append(state)
            self.__n_state += 1
            updated = True
        else:
            self.__states[i], updated = self.__states[i].merge(
                state, return_update=True
            )
        return (
            (self, self.__states[i], updated)
            if return_updated
            else (self, self.__states[i])
        )

    def find(self, arules):
        for i, state in enumerate(self.__states):
            if state == arules:
                return i
        return -1

    def __len__(self):
        return self.__n_state

    def __getitem__(self, idx):
        return self.__states[idx]


class Edge:

    __slots__ = ["__from", "__to", "__var"]

    def __init__(self, from_state, to_state, variable):
        self.__from = from_state
        self.__to = to_state
        self.__var = variable

    def __repr__(self):
        return self.__from.name + " -> " + str(self.__var) + " -> " + self.__to.name

    @property
    def I(self):
        return self.__from

    @property
    def X(self):
        return self.__var

    @property
    def J(self):
        return self.__to

    def __eq__(self, other):
        if self.__from != other.I:
            return False
        if self.__var != other.X:
            return False
        if self.__to != other.J:
            raise DoublePointingEdge(
                "[Error] Edge {}: New edge comes that points {}.".format(
                    self, other.J.name
                )
            )
        return True


class EdgeSet:

    __slot__ = ["__edges"]

    def __init__(self):
        self.__edges = []

    def add(self, edge):
        if edge not in self.__edges:
            self.__edges.append(edge)
        return self

    def __len__(self):
        return len(self.__edges)

    def __getitem__(self, idx):
        return self.__edges[idx]

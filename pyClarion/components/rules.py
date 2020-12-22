"""Tools for creating, managing, and processing rules."""


__all__ = ["Rule", "Rules", "AssociativeRules", "ActionRules"]


from ..base import (
    ConstructType, Symbol, SymbolTrie, Propagator, UpdaterS, rule, chunk
)
from .. import numdicts as nd

from typing import (
    Mapping, MutableMapping, TypeVar, Generic, Type, Dict, FrozenSet, Set, 
    overload, cast
)
from types import MappingProxyType


class Rule(object):
    """Represents a rule form."""

    __slots__ = ("_conc", "_weights")

    def __init__(
        self, conc: chunk, *conds: chunk, weights: Dict[chunk, float] = None
    ):
        """
        Initialize a new rule.

        If conditions contains items that do not appear in weights, weights is 
        extended to map each of these items to a weight of 1. If weights is 
        None, every cond is assigned a weight of 1. 

        If the weights sum to more than 1.0, weights is renormalized such that 
        each weight w is mapped to w / sum(weights.values()).

        :param conclusion: A chunk symbol for the rule conclusion.
        :param conditions: A sequence of chunk symbols representing rule 
            conditions.
        :param weights: An optional mapping from condition chunk symbols 
            to condition weights.
        """

        # preconditions
        if weights is not None:
            if not set(conds).issuperset(weights): 
                ValueError("Keys of arg `weights` do not match conds.")
            if not all(0 < v for v in weights.values()):
                ValueError("Weights must be strictly positive.")

        ws = nd.MutableNumDict(weights)
        ws.extend(conds, value=1.0)

        w_sum = nd.val_sum(ws)
        if w_sum > 1.0: 
            ws /= w_sum

        self._conc = conc
        self._weights = nd.freeze(ws)

        # postconditions
        assert set(self._weights) == set(conds), "Each cond must have a weight."
        assert nd.val_sum(ws) <= 1, "Inferred weights must sum to one or less."

    def __repr__(self) -> str:

        return "Rule(conc={}, weights={})".format(self.conc, self.weights)

    def __eq__(self, other) -> bool:

        if isinstance(other, Rule):
            b = (
                self.conc == other.conc and 
                nd.isclose(self.weights, other.weights)
            )
            return b
        else:
            return NotImplemented

    @property
    def conc(self) -> chunk:
        """Conclusion of rule."""

        return self._conc

    @property
    def weights(self) -> nd.NumDict:
        """Conditions and condition weights of rule."""

        return self._weights

    def strength(self, strengths: nd.NumDict) -> float:
        """
        Compute rule strength given condition strengths.
        
        The rule strength is computed as the weighted sum of the condition 
        strengths in strengths.

        Implementation based on p. 60 and p. 73 of Anatomy of the Mind.
        """

        weighted = nd.keep(strengths, keys=self.weights) * self.weights
        
        return nd.val_sum(weighted)


Rt = TypeVar("Rt", bound="Rule")
class Rules(MutableMapping[rule, Rt], Generic[Rt]):
    """
    A simple rule database.

    Rules are stored in a dict of the form:

    {
        rule(1): Rule(
            conc=chunk("conc1"),
            weights={cond1: w1, ..., condn: wn}
        ),
        ... # other rules
    }            
    """

    # TODO: Updater and update requests need testing. - Can 

    class Updater(UpdaterS):
        """
        Applies requested updates to a client Rules instance.
        
        Assumes any updates will be issued by constructs subordinate to 
        self.client.
        """

        _serves = ConstructType.container_construct

        def __init__(self, rules: "Rules") -> None:
            """Initialize a Rules.Updater instance."""

            self.rules = rules

        @property
        def expected(self):

            return frozenset()

        def __call__(self, inputs, output, update_data):
            """Resolve all outstanding rule database update requests."""

            self.rules.resolve_requests()

    @overload
    def __init__(self: "Rules[Rule]") -> None:
        ...

    @overload
    def __init__(self: "Rules[Rule]", *, max_conds: int) -> None:
        ...

    @overload
    def __init__(self, *, rule_type: Type[Rt]) -> None:
        ...

    @overload
    def __init__(self, *, max_conds: int, rule_type: Type[Rt]) -> None:
        ...

    @overload
    def __init__(
        self, data: Mapping[rule, Rt], max_conds: int, rule_type: Type[Rt]
    ) -> None:
        ...

    def __init__(
        self, 
        data: Mapping[rule, Rt] = None,
        max_conds: int = None,
        rule_type: Type[Rt] = None
    ) -> None:

        if data is None:
            data = dict()
        else:
            data = dict(data)

        self._data = data
        self.max_conds = max_conds
        self.Rule = rule_type if rule_type is not None else Rule

        self._add_promises: MutableMapping[rule, Rt] = dict()
        self._del_promises: Set[rule] = set()
        self._updater = type(self).Updater(self)

    def __repr__(self):

        repr_ = "{}({})".format(type(self).__name__, repr(self._data))
        return repr_

    def __len__(self):

        return len(self._data)

    def __iter__(self):

        yield from iter(self._data)

    def __getitem__(self, key):

        return self._data[key]

    def __setitem__(self, key, val):

        self._validate_rule_form(val)
        if isinstance(val, self.Rule):
            self._data[key] = val
        else:
            msg = "This rule database expects rules of type '{}'." 
            TypeError(msg.format(type(self.Rule.__name__)))

    def __delitem__(self, key):

        del self._data[key]

    @property
    def updater(self):
        """Updater object for bound to self."""

        return self._updater

    @property
    def add_promises(self):
        """A view of promised updates."""

        return MappingProxyType(self._add_promises)

    def define(
        self, 
        r: rule, 
        conc: chunk, 
        *conds: chunk, 
        weights: Dict[chunk, float] = None
    ) -> rule:
        """
        Add a new rule.
        
        Returns the rule symbol.
        """

        self[r] = self.Rule(conc, *conds, weights=weights)

        return r

    def contains_form(self, form):
        """
        Check if the rule set contains a given rule form.
        
        See Rule for details on rule forms.
        """

        return any(form == entry for entry in self.values())

    def request_add(self, r, form):
        """
        Inform self of a new rule to be applied at a later time.
        
        Adds (r, form) to an internal future update dict. Upon call to 
        self.resolve_requests(), the update dict will be passed as an 
        argument to self.update(). 
        
        Will overwrite existing rule if r is already member of self. Does 
        not check for duplicate forms. Will throw an error if an update is 
        already registered for rule r.

        Does not validate the rule form before registering the request. 
        Validation occurs at update time. 
        """

        if r in self._add_promises or r in self._del_promises:
            msg = "Rule {} already registered for a promised update."
            raise ValueError(msg.format(r))
        else:
            self._add_promises[r] = form

    def request_del(self, r: rule) -> None:
        """
        Inform self of an existing rule to be removed at update time.

        Adds r to a future deletion set. Upon a call to resolve_requests(), 
        every member of the deletion set will be removed. If r is not already 
        a member of self, will raise an error.
        """

        if r in self._add_promises or r in self._del_promises:
            msg = "Rule {} already registered for a promised update."
            raise ValueError(msg.format(r))
        elif r not in self:
            raise ValueError("Cannot delete non-existent rule.")
        else:
            self._del_promises.add(r)

    def resolve_requests(self):
        """
        Apply any promised updates (see Rules.request_add()).
        
        Clears promised update dict upon completion.
        """

        for r in self._del_promises:
            del self[r]
        self._del_promises.clear()

        self.update(self._add_promises)
        self._add_promises.clear()

    def _validate_rule_form(self, form):

        if self.max_conds is not None and len(form.weights) > self.max_conds:
            msg = "Received rule with {} conditions; maximum allowed is {}."
            raise ValueError(msg.format(len(form.weights), self.max_conds))


class AssociativeRules(Propagator):
    """
    Propagates activations among chunks through associative rules.
    
    The strength of the conclusion is calculated as a weighted sum of condition 
    strengths. In cases where there are multiple rules with the same conclusion, 
    the maximum is taken. 

    Implementation based on p. 73-74 of Anatomy of the Mind.
    """

    _serves = ConstructType.flow_tt

    def __init__(self, source: Symbol, rules: Rules) -> None:

        self.source = source
        self.rules = rules

    @property
    def expected(self) -> FrozenSet[Symbol]:

        return frozenset((self.source,))

    def call(self, inputs: SymbolTrie[nd.NumDict]) -> nd.NumDict:

        strengths = inputs[self.source]
        if not isinstance(strengths, nd.NumDict):
            raise TypeError("Input must be of type NumDict.")

        d = nd.MutableNumDict(default=0.0)
        for r, form in self.rules.items():
            s_r = form.strength(strengths)
            d[form.conc] = max(d[form.conc], s_r)
            d[r] = s_r
        d.squeeze()

        assert d.default == 0, "Unexpected output default."

        return d


class ActionRules(Propagator):
    """
    Propagates activations from condition to action chunks using action rules.
    
    Action rules compete to be selected based on their rule strengths, which is 
    equal to the product of an action rule's weight and the strength of its 
    condition chunk. The rule strength of the selected action is then 
    propagated to its conclusion. 
    """

    _serves = ConstructType.flow_tt

    def __init__(
        self, source: Symbol, rules: Rules, temperature: float = .01
    ) -> None:

        if rules.max_conds is None or rules.max_conds > 1:
            msg = "Rule database must not accept multiple condition rules."
            raise ValueError(msg)

        self.source = source
        self.rules = rules
        self.temperature = temperature

    @property
    def expected(self) -> FrozenSet[Symbol]:

        return frozenset((self.source,))

    def call(self, inputs: SymbolTrie[nd.NumDict]) -> nd.NumDict:

        # preconditions
        strengths = inputs[self.source]
        if not isinstance(strengths, nd.NumDict):
            raise TypeError("Input must be of type NumDict.")

        d = nd.MutableNumDict(default=0)
        for r, form in self.rules.items():
            d[r] = form.strength(strengths)

        probabilities = nd.boltzmann(d, self.temperature)
        selection = nd.draw(probabilities, n=1)

        d *= selection
        d.squeeze()
        d.max(nd.transform_keys(d, func=lambda r: self.rules[r].conc))

        # postconditions
        assert d.default == 0, "Unexpected output default."

        return d

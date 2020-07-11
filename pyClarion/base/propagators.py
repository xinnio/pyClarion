"""Provides abstract classes for defining forward propagation cycles."""


__all__ = [
    "Propagator", "PropagatorA", "PropagatorR", "PropagatorB", 
    "Cycle", "CycleS", "CycleG"
]


from pyClarion.base.symbols import ConstructSymbol, MatchSpec, ConstructType
from pyClarion.base.packets import (
    ActivationPacket, ResponsePacket, SubsystemPacket
)
from pyClarion.utils.funcs import simple_junction
from typing import (
    TypeVar, Generic, Mapping, Callable, Any, Mapping, Tuple, Set, Dict, 
    Sequence, Optional
)
from abc import abstractmethod


T = TypeVar('T', bound="Propagator")
Dt = TypeVar('Dt') # type variable for inputs to processes
It = TypeVar('It', contravariant=True) # type variable for propagator inputs
Xt = TypeVar('Xt') # type variable for intermediate stage 
                   # Should Xt be covariant/contravariant? - Can 
Ot = TypeVar('Ot', covariant=True) # type variable for propagator outputs

PullFuncs = Mapping[ConstructSymbol, Callable[[], Dt]]
Inputs = Mapping[ConstructSymbol, Dt]
APData = Mapping[ConstructSymbol, Any] # type for ActivationPacket init
DPData = Tuple[APData, Set[ConstructSymbol]] # type for ResponsePacket init
SPData = Tuple[
    Mapping[ConstructSymbol, ActivationPacket],
    Mapping[ConstructSymbol, ResponsePacket]
]

class Propagator(Generic[It, Xt, Ot]):
    """
    Abstract class for propagating strengths, decisions, and states.

    Propagator subclasses and instances define how constructs process inputs 
    and set outputs.
    """

    matches: MatchSpec

    def __init__(self, matches: MatchSpec = None):

        self.matches = matches if matches is not None else MatchSpec()

    def __copy__(self: T) -> T:
        """
        Make a copy of self.
        
        This method is primarily for use in factory patterns where a propagator 
        instance may be provided as a template. The copy method should ensure 
        that copies of the template instance may be mutated without unwanted 
        mutation of other instances derived from the template.
        """
        raise NotImplementedError() 

    def __call__(
        self, construct: ConstructSymbol, inputs: PullFuncs[It], **kwds: Any
    ) -> Ot:
        """
        Execute construct's forward propagation cycle.

        Wrapper for self.call().

        Pulls data from inputs constructs, delegates processing to self.call(),
        and wraps result in appropriate Packet instance.
        """

        inputs_ = {source: pull_func() for source, pull_func in inputs.items()}
        intermediate: Xt = self.call(construct, inputs_, **kwds)
        
        return self.make_packet(intermediate)

    def expects(self, construct: ConstructSymbol):
        """Returns True if propagator expects input from given construct."""

        return construct in self.matches

    def make_packet(self, data: Xt = None) -> Ot:
        raise NotImplementedError()

    @abstractmethod
    def call(
        self, construct: ConstructSymbol, inputs: Inputs[It], **kwds: Any
    ) -> Xt:
        """
        Execute construct's forward propagation cycle.

        :param construct: The construct symbol associated with the realizer 
            owning to the propagation callback. 
        :param inputs: A dictionary, mapping construct symbols to Packet 
            instances, specifying input passed to the owning construct by other 
            constructs within the simulation. 
        :param kwargs: Any additional parameters passed to the call to owning 
            construct's propagate() method through the `options` argument. These 
            arguments may be used to contextually modify propagator behavior, 
            pass in external inputs, etc. For ease of debugging and as a 
            precaution against subtle bugs (e.g., failing to set an option due 
            to misspelled keyword argument name) it is recommended that 
            Propagator instances throw errors upon receipt of unexpected 
            keyword arguments.
        """
        raise NotImplementedError()


class PropagatorA(Propagator[ActivationPacket, APData, ActivationPacket]):
    """
    Represents a propagator for nodes or flows.

    Maps activations to activations.
    """

    def make_packet(self, data: APData = None) -> ActivationPacket:

        data = data if data is not None else dict()
        return ActivationPacket(mapping=data)


class PropagatorR(Propagator[ActivationPacket, DPData, ResponsePacket]):
    """
    Represents a propagator for response selection.

    Maps activations to decisions.
    """

    def make_packet(self, data: DPData = None) -> ResponsePacket:

        mapping, selection = data if data is not None else (dict(), set())
        return ResponsePacket(mapping=mapping, selection=selection)


class PropagatorB(Propagator[SubsystemPacket, APData, ActivationPacket]):
    """
    Represents a propagator for buffers.

    Maps subsystem outputs to activations.
    """
    
    def make_packet(self, data: APData = None) -> ActivationPacket:

        data = data if data is not None else dict()
        return ActivationPacket(mapping=data)


class Cycle(Generic[It, Xt, Ot]):
    """Represents a container construct activation cycle."""

    # Specifies data required to construct the output packet
    output: Optional[Sequence[ConstructType]] = None

    def __init__(self, sequence, matches: MatchSpec = None):

        self.sequence = sequence
        self.matches = matches if matches is not None else MatchSpec()

    def expects(self, construct: ConstructSymbol) -> bool:
        """Returns True if propagator expects input from given construct."""

        return construct in self.matches

    def make_packet(self, data: Xt = None) -> Ot:
        raise NotImplementedError()


class CycleS(Cycle[ActivationPacket, SPData, SubsystemPacket]):
    """Represents a subsystem activation cycle."""

    output = (ConstructType.node, ConstructType.response)

    def __init__(self, sequence, matches: MatchSpec = None):

        super().__init__(
            sequence=sequence,
            matches=matches
        )

    def make_packet(self, data: SPData = None) -> SubsystemPacket:

        mapping, decisions = data if data is not None else (dict(), dict())
        mapping = simple_junction(mapping.values())

        return SubsystemPacket(mapping=mapping, decisions=decisions)


class CycleG(Cycle[None, None, None]):
    """Represents an aGent activation cycle."""
    pass
    
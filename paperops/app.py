"""Service wiring for the control console."""

from dataclasses import dataclass
from typing import Any

from .audit import AuditLog, AuditService
from .broke import BrokeService
from .cal import CalService
from .clock import IdSequence, LogicalClock
from .config import Config
from .console.router import Console
from .dry import DryService
from .event import EventBus
from .glue import GlueService
from .press import PressService
from .reel import ReelService
from .state import StateService
from .steam import SteamService
from .store import Journal
from .verdict import BatchRegistry
from .version import Artifacts, Confirmations, Generations
from .water import WaterService


@dataclass
class Services:
    """Every subsystem wired together, with the console in front of them."""

    config: Config
    journal: Journal
    bus: EventBus
    clock: LogicalClock
    generations: Generations
    confirmations: Confirmations
    artifacts: Artifacts
    batches: BatchRegistry
    press: PressService
    dry: DryService
    steam: SteamService
    glue: GlueService
    cal: CalService
    reel: ReelService
    broke: BrokeService
    water: WaterService
    audit: AuditService
    state: StateService
    console: Any = None

    def reload(self) -> None:
        """Restore every subsystem from the committed part of the stream."""
        self.press.reload()
        self.steam.reload()
        self.dry.reload()
        self.glue.reload()
        self.cal.reload()
        self.reel.reload()
        self.broke.reload()
        self.water.reload()


def build_services(config: Config) -> Services:
    """Wire the whole service from a configuration."""
    journal = Journal(config.data_dir)
    bus = EventBus()
    clock = LogicalClock()
    generations = Generations(journal)
    confirmations = Confirmations(journal, clock, IdSequence("cfm"), generations)
    artifacts = Artifacts(journal, clock)
    batches = BatchRegistry(journal)

    press = PressService(journal, bus, clock, generations, confirmations)
    steam = SteamService(journal, bus, clock, generations, confirmations)
    dry = DryService(journal, bus, clock, generations, confirmations)
    glue = GlueService(journal, bus, clock, generations, confirmations)
    cal = CalService(journal, bus, clock)
    reel = ReelService(journal, bus, clock)
    broke = BrokeService(journal, bus, clock, batches)
    water = WaterService(journal, bus, clock, generations, confirmations)
    audit = AuditService(AuditLog(config.data_dir), bus, clock)
    state = StateService(
        journal,
        bus,
        clock,
        generations,
        artifacts,
        subsystems={
            "press": press,
            "dry": dry,
            "steam": steam,
            "glue": glue,
            "cal": cal,
            "reel": reel,
            "broke": broke,
            "water": water,
        },
        histories={
            "press.dryness": press.history(),
            "steam.pressure": steam.history(),
            "glue.concentration": glue.history(),
            "broke.handling": broke.history(),
            "water.moisture": water.history(),
        },
    )

    services = Services(
        config=config,
        journal=journal,
        bus=bus,
        clock=clock,
        generations=generations,
        confirmations=confirmations,
        artifacts=artifacts,
        batches=batches,
        press=press,
        dry=dry,
        steam=steam,
        glue=glue,
        cal=cal,
        reel=reel,
        broke=broke,
        water=water,
        audit=audit,
        state=state,
    )
    services.reload()
    dry.wire()
    glue.wire()
    water.wire()
    audit.wire()
    state.wire()
    services.console = Console(services)
    return services

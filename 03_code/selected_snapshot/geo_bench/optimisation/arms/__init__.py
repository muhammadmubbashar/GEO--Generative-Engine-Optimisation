"""ARM_REGISTRY — name → Arm instance."""
from .position_control import PositionControlArm
from .ssr_visible import SsrVisibleArm
from .ssr_visible_digitfix import SsrVisibleDigitfixArm
from .ssr_visible_twin import SsrVisibleTwinArm
from .schema_markup import SchemaMarkupArm
from .faq_structure import FaqStructureArm
from .faq_structure_route import FaqStructureRouteArm
from .freshness_signal import FreshnessSignalArm
from .statistics_addition import StatisticsAdditionArm
from .statistics_addition_twin import StatisticsAdditionTwinArm
from .cite_sources import CiteSourcesArm
from .keyword_stuffing import KeywordStuffingArm
from .padding_control import PaddingControlArm
from .stats_cite_combined import StatsCiteCombinedArm

ARM_REGISTRY = {
    "position_control": PositionControlArm(),
    "ssr_visible": SsrVisibleArm(),
    "ssr_visible_digitfix": SsrVisibleDigitfixArm(),
    "ssr_visible_twin": SsrVisibleTwinArm(),
    "schema_markup": SchemaMarkupArm(),
    "faq_structure": FaqStructureArm(),
    "faq_structure_route": FaqStructureRouteArm(),
    "freshness_signal": FreshnessSignalArm(),
    "statistics_addition": StatisticsAdditionArm(),
    "statistics_addition_twin": StatisticsAdditionTwinArm(),
    "cite_sources": CiteSourcesArm(),
    "keyword_stuffing": KeywordStuffingArm(),
    "padding_control": PaddingControlArm(),
    "stats_cite_combined": StatsCiteCombinedArm(),
}

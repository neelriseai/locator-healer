"""Strategy catalog."""

from xpath_healer.core.strategies.attribute_strategy import AttributeStrategy
from xpath_healer.core.strategies.axis_hint_field import AxisHintFieldResolverStrategy
from xpath_healer.core.strategies.button_text_candidate import ButtonTextCandidateStrategy
from xpath_healer.core.strategies.checkbox_icon_by_label import CheckboxIconByLabelStrategy
from xpath_healer.core.strategies.composite_label_control import CompositeLabelControlStrategy
from xpath_healer.core.strategies.generic_template import GenericTemplateStrategy
from xpath_healer.core.strategies.grid_cell_colid import GridCellByColIdStrategy
from xpath_healer.core.strategies.label_proximity_interactable import LabelProximityInteractableStrategy
from xpath_healer.core.strategies.multi_field_text_resolver import MultiFieldTextResolverStrategy
from xpath_healer.core.strategies.position_fallback import PositionFallbackStrategy
from xpath_healer.core.strategies.text_occurrence import TextOccurrenceStrategy
from xpath_healer.core.strategies.tree_toggle_by_label import TreeToggleByLabelStrategy

__all__ = [
    "GenericTemplateStrategy",
    "AxisHintFieldResolverStrategy",
    "CompositeLabelControlStrategy",
    "LabelProximityInteractableStrategy",
    "ButtonTextCandidateStrategy",
    "CheckboxIconByLabelStrategy",
    "TreeToggleByLabelStrategy",
    "MultiFieldTextResolverStrategy",
    "AttributeStrategy",
    "GridCellByColIdStrategy",
    "TextOccurrenceStrategy",
    "PositionFallbackStrategy",
]

from typing import Dict, List, Any
from .base import BaseRule

class RuleRegistry:
    """
    Global registry for Validation Rules and Packs in Audit OS.
    """
    _rules: Dict[str, BaseRule] = {}
    _packs: Dict[str, Any] = {} # BaseValidationPack loaded dynamically

    @classmethod
    def register_rule(cls, rule: BaseRule):
        cls._rules[rule.rule_id] = rule

    @classmethod
    def register_pack(cls, pack):
        cls._packs[pack.pack_name] = pack
        for rule in pack.get_rules():
            cls.register_rule(rule)

    @classmethod
    def get_rule(cls, rule_id: str) -> BaseRule:
        return cls._rules.get(rule_id)

    @classmethod
    def get_all_rules(cls) -> List[BaseRule]:
        return list(cls._rules.values())

    @classmethod
    def get_all_packs(cls) -> List[Any]:
        return list(cls._packs.values())

    @classmethod
    def clear(cls):
        cls._rules.clear()
        cls._packs.clear()

# Add standard import helper
import sys
from typing import Any

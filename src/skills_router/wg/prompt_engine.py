"""Dynamic Workspace/Global Template Engine.

Selects and renders the appropriate Workspace/Global prompt for a given case,
and provides the available options for user selection.
"""

from __future__ import annotations

from skills_router.wg.templates import TEMPLATES


class PromptEngine:
    """Renders Workspace/Global prompts and provides option lists."""

    def __init__(self, max_items: int = 5, max_chars: int = 1400):
        self.max_items = max(1, max_items)
        self.max_chars = max(400, max_chars)

    def render(self, wg_case: str, context: dict) -> str:
        """Render the Workspace/Global prompt for a given case.

        Args:
            wg_case: Case identifier (e.g. ``"CASE_1"``, ``"CASE_DEP"``).
            context: Template variables dict.

        Returns:
            Formatted prompt string.

        Raises:
            ValueError: If the case is not recognised.
        """
        entry = TEMPLATES.get(wg_case)
        if entry is None:
            raise ValueError(f"Unknown WG case: {wg_case}")
        render_fn, _options_fn = entry
        prompt = render_fn(self._prepare_context(context))
        return self._clip(prompt)

    def get_options(self, wg_case: str, **kwargs) -> list[str]:
        """Return the list of user options for a given case.

        Args:
            wg_case: Case identifier.
            **kwargs: Passed to the options function (e.g. ``extensible=True``
                      for CASE_2).

        Returns:
            List of option strings.
        """
        entry = TEMPLATES.get(wg_case)
        if entry is None:
            raise ValueError(f"Unknown WG case: {wg_case}")
        _render_fn, options_fn = entry
        return options_fn(**kwargs)

    def render_full(
        self, wg_case: str, context: dict, **options_kwargs
    ) -> tuple[str, list[str]]:
        """Render prompt and options together.

        Returns:
            Tuple of (rendered_prompt, options_list).
        """
        prompt = self.render(wg_case, context)
        options = self.get_options(wg_case, **options_kwargs)
        return prompt, options

    def _prepare_context(self, context: dict) -> dict:
        prepared = dict(context)
        prepared.setdefault("_max_items", self.max_items)
        return prepared

    def _clip(self, prompt: str) -> str:
        if len(prompt) <= self.max_chars:
            return prompt
        return prompt[: self.max_chars].rstrip() + "\n... truncated; inspect the manifest for full details."

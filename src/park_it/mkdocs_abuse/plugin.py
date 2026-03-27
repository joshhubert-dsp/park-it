from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path

from jinja2 import (
    ChoiceLoader,
    Environment,
    PackageLoader,
    StrictUndefined,
    select_autoescape,
)
from mkdocs.config import config_options
from mkdocs.config.base import (
    Config,
)
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.exceptions import ConfigurationError
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page
from pydantic import BaseModel, ValidationError

from park_it.models.app_config import AppConfig
from park_it.models.field_types import YamlPath
from park_it.models.space import get_space_type_emoji

# mkdocs assets directories
EVIL_ROOT = Path(str(importlib.resources.files("park_it.mkdocs_abuse")))
ASSETS_SRC = EVIL_ROOT / "assets"
TEMPLATES_SRC = EVIL_ROOT / "templates"
CSS_ASSETS = [css.name for css in ASSETS_SRC.glob("*.css")]
JS_ASSETS = [js.name for js in ASSETS_SRC.glob("*.js")]
APP_MD_NAME = "app"

# asset destinations in built site/ dir
TEMPLATES_DEST = Path("templates")
# copy JS/CSS from package into site/ and auto-include them in pages.
ASSETS_DEST = Path("assets/park-it")
IMAGES_DEST = ASSETS_DEST / "images"

REMOTE_JS = [
    "https://unpkg.com/htmx.org@1.9.12",
    "https://unpkg.com/htmx.org/dist/ext/sse.js",
]


# TODO args for switching theme tweaks
class ParkItPluginConfig(Config):
    """
    MkDocs plugin configuration schema.
    MkDocs reads these from mkdocs.yml and validates/coerces types.
    """

    app_config = config_options.Type(str, default=str(Path.cwd() / "app-config.yaml"))
    assets_enabled = config_options.Type(bool, default=True)


class ConfigValidator(BaseModel):
    app_config: YamlPath
    assets_enabled: bool


class ParkItPlugin(BasePlugin[ParkItPluginConfig]):
    """
    MkDocs plugin that generates resource reservation pages from YAML configs.

    User config example in mkdocs.yml:

    plugins:
      - park-it
    """

    def __init__(self):
        super().__init__()

        # Map virtual src_path -> generated Markdown content.
        # MkDocs will ask us "what is the source for this page?" later.
        self._generated_markdown: dict[str, str] = {}
        # Stash resources so multiple hooks can access them.
        self.app_config: AppConfig | None = None

        # Jinja environment for rendering templates to produce a virtual markdown file
        # with frontmatter used by the mkdocs build
        # - PackageLoader points at park_it_mkdocs/templates
        # - StrictUndefined makes missing variables fail loudly (good for debugging)
        self._jinja = Environment(
            loader=PackageLoader("park_it", "mkdocs_abuse/templates"),
            undefined=StrictUndefined,
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # --- HOOKS ---
    def on_config(self, config: MkDocsConfig):
        """
        Called early. Great place to:
        - inject extra JS/CSS into MkDocs config so user doesn't have to
        - normalize paths
        - read basic settings

        IMPORTANT:
        - This runs before rendering begins.
        """

        try:
            self.cfg = ConfigValidator.model_validate(self.config)
        except ValidationError as e:
            # MkDocs wants ConfigurationError for pretty output
            raise ConfigurationError(str(e)) from e

        self.app_config = AppConfig.from_yaml(self.cfg.app_config)
        self.root_path = self.cfg.app_config.parent
        config["site_name"] = self.app_config.title

        config["extra_javascript"] += REMOTE_JS

        if self.cfg.assets_enabled:
            # MkDocs will emit <script src="..."> for each entry in extra_javascript.
            # It will emit <link rel="stylesheet" href="..."> for each entry in extra_css.
            config["extra_javascript"] += [str(ASSETS_DEST / js) for js in JS_ASSETS]
            config["extra_css"] += [str(ASSETS_DEST / css) for css in CSS_ASSETS]

        return config

    def on_env(self, env: Environment, /, *, config: MkDocsConfig, files: Files):
        """
        Add plugin templates to the Jinja loader search path.
        This makes `template: pi-form.html` resolvable.
        """
        plugin_loader = PackageLoader("park_it", "mkdocs_abuse/templates")
        existing_loader = env.loader

        # Put plugin loader AFTER user's overrides but BEFORE theme defaults.
        # Usually env.loader is already a ChoiceLoader; we just extend it.
        if isinstance(existing_loader, ChoiceLoader):
            loaders = list(existing_loader.loaders)
            env.loader = ChoiceLoader(loaders + [plugin_loader])
        else:
            env.loader = ChoiceLoader(
                [
                    loader
                    for loader in [existing_loader, plugin_loader]
                    if loader is not None
                ]
            )

        env.filters["emoji"] = get_space_type_emoji
        return env

    def on_files(self, files: Files, /, *, config: MkDocsConfig) -> Files:
        """
        MkDocs calls this with the discovered set of documentation source files.

        We can add additional virtual pages by appending mkdocs.structure.files.File objects.

        These files do NOT have to exist on disk if we also implement on_page_read_source
        to supply their contents as strings.
        """
        template_path = f"{APP_MD_NAME}.md"
        self._generated_markdown[template_path] = self._render_page_md(template_path)

        # Add file to MkDocs "known files". MkDocs uses docs_dir for source root,
        # but the file doesn't actually need to exist because we'll provide content later.
        files.append(
            File(
                path=template_path,  # doc-relative path
                src_dir=None,  # virtual file
                # output root, arg already available at yaml top level
                dest_dir=config["site_dir"],
                use_directory_urls=True,
            )
        )

        return files

    def on_page_read_source(self, /, *, page: Page, config: MkDocsConfig) -> str | None:
        """
        MkDocs calls this when it wants the *source Markdown text* for a page.

        For our virtual pages, return the generated Markdown string.
        For all other pages, return None to let MkDocs read from disk normally.
        """
        return self._generated_markdown.get(page.file.src_path)

    def on_post_build(self, *, config: MkDocsConfig) -> None:
        """
        Called after MkDocs has rendered the site into `site/`.

        Perfect time to copy packaged JS/CSS assets into the final output folder,
        so that URLs we injected via extra_javascript/extra_css actually resolve.

        This does NOT modify the user's repo. It only affects the built output.
        """
        if not self.cfg.assets_enabled:
            return

        # Built site directory (where MkDocs outputs HTML/CSS/JS).
        dest_dir = config["site_dir"] / ASSETS_DEST
        dest_dir.mkdir(parents=True)
        for name in JS_ASSETS + CSS_ASSETS:
            src = ASSETS_SRC / name
            if not src.exists():
                raise FileNotFoundError(f"park-it asset missing from package: {src}")
            shutil.copy2(src, dest_dir / name)

        # copy over images, if provided
        assert self.app_config is not None
        image_rel_path = self.app_config.image.path if self.app_config.image else None
        if image_rel_path:
            image_dest_dir = config["site_dir"] / IMAGES_DEST
            image_dest_dir.mkdir(parents=True)
            shutil.copy2(
                self.root_path / image_rel_path, image_dest_dir / image_rel_path
            )

        self._copy_built_html_to_templates_dir(config)

    # --- HELPERS ---

    def _render_page_md(self, template_name: str) -> str:
        """
        Custom Jinja step renders resource page Markdown using a template shipped in this package.
        Makes use of yaml frontmatter in the markdown page.
        """
        assert self.app_config is not None
        if self.app_config.image:
            image_path = (IMAGES_DEST / self.app_config.image.path).as_posix()
        else:
            image_path = None

        tpl = self._jinja.get_template(f"{template_name}.j2")
        return tpl.render(config=self.app_config, image_path=image_path)

    def _copy_built_html_to_templates_dir(self, config) -> None:
        site_dir = Path(config["site_dir"])
        src = site_dir / APP_MD_NAME / "index.html"
        template_dest = site_dir / TEMPLATES_DEST / "index.html"
        template_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, template_dest)

        example_dest = site_dir / "index.html"
        template_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, example_dest)

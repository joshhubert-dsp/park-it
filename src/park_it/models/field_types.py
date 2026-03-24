"""
Definitions of custom types for `AppConfig` fields.
"""

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, FilePath
from pydantic.functional_validators import AfterValidator


def must_be_yaml(p: Path) -> Path:
    """Validate that a path points to a YAML file.

    Args:
        p (Path): Path to validate.

    Returns:
        Path: The original path when its suffix is `.yaml` or `.yml`.

    Raises:
        ValueError: If the path does not end in `.yaml` or `.yml`.
    """
    if p.suffix.lower() != ".yaml" and p.suffix.lower() != ".yml":
        raise ValueError(f"'{p}' must be a yaml file")
    return p


YamlPath = Annotated[FilePath, AfterValidator(must_be_yaml)]


class ImageFile(BaseModel):
    """Image metadata for content rendered by the site.

    If both pixel dimensions are omitted, the rendered image uses its original size. If
    only one dimension is provided, the other is inferred to preserve aspect ratio.

    Attributes:
        path (Path): Image file path relative to the project root.
        caption (str, optional): Caption text displayed with the image. Defaults to "".
        pixel_width (int | None, optional): Desired rendered width in pixels, if
            overriding the source image. Defaults to None.
        pixel_height (int | None, optional): Desired rendered height in pixels, if
            overriding the source image. Defaults to None.
    """

    path: Path
    caption: str = ""
    pixel_width: int | None = None
    pixel_height: int | None = None

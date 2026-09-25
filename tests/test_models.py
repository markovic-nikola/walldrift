import pytest

from .conftest import candidate

SCREEN = (2560, 1440)  # 16:9


@pytest.mark.parametrize(
    ("size", "fits"),
    [
        ((3840, 2160), True),  # same shape
        ((2560, 1440), True),  # exactly the screen
        ((2559, 1440), False),  # too narrow to cover it
        ((4000, 3000), True),  # 4:3 crops a quarter
        ((8160, 6144), True),  # a near-4:3 camera photo crops 25.3%
        ((5000, 4000), False),  # 5:4 crops 30%
        ((5120, 2160), True),  # 21:9 crops under a quarter
        ((7680, 2160), False),  # 32:9 panorama crops half
        ((2160, 3840), False),  # portrait
        ((4000, 4000), False),  # square
    ],
)
def test_fits_checks_size_and_shape(size: tuple[int, int], fits: bool) -> None:
    width, height = size
    assert candidate(1, width=width, height=height).fits(*SCREEN) is fits

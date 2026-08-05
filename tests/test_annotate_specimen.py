import pandas as pd

from annotate_specimen import LineAnnotator, _fill_mm_columns, polygon_area_px


def test_polygon_area_of_a_known_rectangle():
    assert polygon_area_px([(0, 0), (10, 0), (10, 5), (0, 5)]) == 50.0


def test_fill_mm_columns_computes_from_matching_calibration():
    calibration = pd.DataFrame(
        [{"px_per_mm": 20.0, "low_confidence_calibration": False}],
        index=pd.Index(["sample_wt01_front-1_ch00"], name="_stem"),
    )
    row = {"length_px": 200.0, "width_px": 100.0, "frame_area_px": 20000.0}
    row = _fill_mm_columns(row, "sample_WT01_FRONT-1_ch00.tif", calibration)
    assert row["length_mm"] == 10.0
    assert row["width_mm"] == 5.0
    assert row["area_mm2"] == 50.0
    assert row["low_confidence_calibration"] is False


def test_fill_mm_columns_leaves_blank_without_a_match():
    calibration = pd.DataFrame(
        [{"px_per_mm": 20.0, "low_confidence_calibration": False}],
        index=pd.Index(["unrelated_file"], name="_stem"),
    )
    row = {"length_px": 200.0, "width_px": 100.0, "frame_area_px": 20000.0}
    row = _fill_mm_columns(row, "sample_WT01_FRONT-1_ch00.tif", calibration)
    assert row["length_mm"] is None
    assert row["width_mm"] is None
    assert row["area_mm2"] is None


def test_fill_mm_columns_leaves_blank_without_any_calibration_loaded():
    row = {"length_px": 200.0, "width_px": 100.0, "frame_area_px": 20000.0}
    row = _fill_mm_columns(row, "sample_WT01_FRONT-1_ch00.tif", None)
    assert row["length_mm"] is None


def test_polygon_area_needs_at_least_three_points():
    assert polygon_area_px([(0, 0), (10, 0)]) == 0.0


def _annotator_without_gui():
    obj = LineAnnotator.__new__(LineAnnotator)
    obj.stage = "frame"
    obj.frame_points = []
    obj.length_points = []
    obj.width_points = []
    obj.finished = False
    obj.redraw = lambda: None  # no real matplotlib figure/axes in these tests
    obj.ax = "AXES"  # sentinel; FakeEvent.inaxes matches this to simulate "inside the plot"
    obj.fig = None
    obj._view_initialized = False
    return obj


def test_click_sequence_advances_through_stages_and_computes_row():
    a = _annotator_without_gui()

    class FakeEvent:
        def __init__(self, x, y):
            self.xdata, self.ydata = x, y
            self.inaxes = "AXES"

    for pt in [(0, 0), (10, 0), (10, 10), (0, 10)]:
        a.on_click(FakeEvent(*pt))
    assert a.stage == "frame"
    assert len(a.frame_points) == 4

    class FakeKeyEvent:
        def __init__(self, key):
            self.key = key

    a.on_key(FakeKeyEvent("n"))
    assert a.stage == "length"

    a.on_click(FakeEvent(1, 1))
    a.on_click(FakeEvent(1, 9))
    assert a.stage == "width"

    a.on_click(FakeEvent(0, 5))
    a.on_click(FakeEvent(10, 5))
    assert a.stage == "done"

    a.on_key(FakeKeyEvent("q"))
    assert a.finished

    row = a.get_row("test.tif")
    assert row["frame_area_px"] == 100.0
    assert row["length_px"] == 8.0
    assert row["width_px"] == 10.0
    assert row["frame_points_px"] == "0.00,0.00;10.00,0.00;10.00,10.00;0.00,10.00"


def test_undo_steps_back_across_stage_boundary():
    a = _annotator_without_gui()
    a.stage = "length"
    a.frame_points = [(0, 0), (1, 1), (2, 2)]
    a.length_points = []
    a._undo()
    assert a.stage == "frame"
    assert a.frame_points == [(0, 0), (1, 1), (2, 2)]  # points untouched, just stepped back


class FakeAxes:
    def __init__(self, xlim, ylim):
        self._xlim = xlim
        self._ylim = ylim

    def get_xlim(self):
        return self._xlim

    def get_ylim(self):
        return self._ylim

    def set_xlim(self, lo, hi):
        self._xlim = (lo, hi)

    def set_ylim(self, lo, hi):
        self._ylim = (lo, hi)


class FakeCanvas:
    def draw(self):
        pass


class FakeFig:
    canvas = FakeCanvas()


def test_scroll_up_zooms_in_centered_on_cursor():
    a = _annotator_without_gui()
    a.ax = FakeAxes(xlim=(0, 100), ylim=(100, 0))  # inverted y, like imshow
    a.fig = FakeFig()

    class FakeScrollEvent:
        inaxes = a.ax
        xdata, ydata = 20, 20
        button = "up"

    a.on_scroll(FakeScrollEvent())

    xlim = a.ax.get_xlim()
    ylim = a.ax.get_ylim()
    assert xlim[1] - xlim[0] < 100  # view shrank (zoomed in)
    assert abs((ylim[0] - ylim[1])) < 100
    assert a._view_initialized


def test_pan_right_shifts_view_toward_larger_x():
    a = _annotator_without_gui()
    a.ax = FakeAxes(xlim=(0, 100), ylim=(100, 0))
    a._pan("right")
    xlim = a.ax.get_xlim()
    assert xlim[0] > 0
    assert xlim[1] - xlim[0] == 100  # width unchanged, just shifted
    assert a._view_initialized


def test_reset_key_clears_view_initialized_flag():
    a = _annotator_without_gui()
    a._view_initialized = True

    class FakeKeyEvent:
        key = "r"

    a.on_key(FakeKeyEvent())
    assert not a._view_initialized

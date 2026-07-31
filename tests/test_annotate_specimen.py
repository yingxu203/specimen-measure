from annotate_specimen import LineAnnotator, polygon_area_px


def test_polygon_area_of_a_known_rectangle():
    assert polygon_area_px([(0, 0), (10, 0), (10, 5), (0, 5)]) == 50.0


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

import itertools as it

from commonplace._progress import checkpoint, track


def test_track():
    for i in track(range(5)):
        print(i)


def test_nested_track():
    for i in track(range(5)):
        for j in track(range(5)):
            print(i, j)


def test_checkpoint():
    with checkpoint() as steps:
        result = list(it.islice(steps, 10))
    assert result == list(range(10))


def test_checkpoint_quiet():
    with checkpoint(quiet=True) as steps:
        result = list(it.islice(steps, 10))
    assert result == list(range(10))

from screentl.events import AppEvent, EventBus, EventKind


def test_event_bus_is_bounded_and_keeps_newest_events():
    bus = EventBus(maxsize=2)
    bus.publish(AppEvent(EventKind.LOG, "test", "one"))
    bus.publish(AppEvent(EventKind.LOG, "test", "two"))
    bus.publish(AppEvent(EventKind.ERROR, "test", "three"))

    messages = [event.message for event in bus.drain()]
    assert messages == ["two", "three"]

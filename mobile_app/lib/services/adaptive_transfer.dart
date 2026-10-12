/// Measured transfers, not the radio label: congested Wi-Fi can be worse than 3G.
class AdaptiveTransfer {
  bool constrained = false;
  int _fastTransfers = 0;

  int get eventLimit => constrained ? 30 : (_fastTransfers >= 2 ? 200 : 50);
  Duration get timeout => Duration(seconds: constrained ? 40 : 25);

  void succeeded(Duration elapsed, int bytes) {
    final double seconds = elapsed.inMilliseconds / 1000;
    if (seconds >= 5 ||
        (bytes >= 8192 && seconds > 1 && bytes / seconds < 8000)) {
      constrained = true;
      _fastTransfers = 0;
    } else if (seconds < 3) {
      _fastTransfers++;
      if (_fastTransfers >= 3) constrained = false;
    } else {
      _fastTransfers = 0;
    }
  }

  void failed() {
    constrained = true;
    _fastTransfers = 0;
  }
}

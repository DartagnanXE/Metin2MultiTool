# -*- coding: utf-8 -*-
"""Pytest-weiter Guard: Tests duerfen NIE den Live-Telemetrie-Server treffen.

Die Default-Submit-URL (interface/config/defaults.py) zeigt auf den echten
Server (telemetry.musketier.net). Mehrere Tests konstruieren eine echte
``App()`` (test_gui_smoke / test_app_controller / test_anon_model_wiring), die
beim Start den Telemetrie-Sender + den Ranking-Out-of-band-Submit anwirft. Ohne
diesen Guard wuerden die mit FRISCHEN Zufalls-install_ids echte Submissions an
die Produktion schicken und das Live-Board verschmutzen.

Wir setzen daher -- BEVOR ein Testmodul importiert/gelaufen ist -- die Opt-out-
Env ``M2FB_NO_TELEMETRY``. ``App._start_telemetry`` und
``ranking_view._submit_current_stats`` honorieren sie und bleiben still. Die
reine Telemetrie-LOGIK (mit expliziten States/Mocks, z. B. test_telemetry_client)
laeuft NICHT ueber diese Pfade und ist davon unberuehrt. Produktion setzt die
Variable nie.
"""

import os

os.environ.setdefault('M2FB_NO_TELEMETRY', '1')

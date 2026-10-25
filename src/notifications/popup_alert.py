"""
DrugShield AI - Native OS Toast Notification Engine (popup_alert.py)
====================================================================
Fires immediate high-visibility OS desktop toast notifications when live passive
crawlers identify a narcotics threat with score >= 0.60.
Utilizes native Windows PowerShell Toast API / plyer for zero-dependency execution.
"""

import sys
import os
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional

FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent

try:
    from plyer import notification
except ImportError:
    notification = None


def _show_windows_toast_powershell(title: str, message: str, threat_score: float):
    """Fires native Windows Toast notification via PowerShell script."""
    clean_title = title.replace('"', '`"').replace("'", "`'")
    clean_msg = message.replace('"', '`"').replace("'", "`'")

    ps_script = f'''
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode("{clean_title}")) > $null
    $textNodes.Item(1).AppendChild($template.CreateTextNode("{clean_msg}")) > $null
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("DrugShield AI OSINT")
    $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
    $notifier.Show($notification)
    '''

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False
        )
    except Exception:
        # Fallback to simple audible bell and system beep
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass


def trigger_threat_popup(
    threat_data: Dict[str, Any],
    title: Optional[str] = None,
    async_call: bool = True
):
    """
    Main entry point to fire immediate OS desktop toast alert when threat score >= 0.60.
    """
    score = threat_data.get("threat_score") or threat_data.get("risk_score") or 0.0
    sender = threat_data.get("sender_id") or threat_data.get("sender_username") or "Unknown Suspect"
    platform = (threat_data.get("platform") or "LIVE STREAM").upper()
    msg_snippet = threat_data.get("message_text") or threat_data.get("message_body") or ""
    if len(msg_snippet) > 85:
        msg_snippet = msg_snippet[:82] + "..."

    drugs = threat_data.get("extracted_entities", {}).get("narcotics_detected", []) or threat_data.get("detected_drugs", [])
    drug_str = f" | Substances: {', '.join(drugs)}" if drugs else ""

    default_title = f"🚨 DRUGSHIELD ALERT [{score:.2f}] - {platform}"
    full_title = title or default_title
    body_text = f"Suspect: {sender}{drug_str}\n\"{msg_snippet}\""

    # Console Alert Banner
    print("\n" + "=" * 68)
    print(f" 🚨 [OS DESKTOP POPUP ALERT FIRED] -> Threat Score: {score:.2f}")
    print(f"    Platform : {platform}")
    print(f"    Author   : {sender}")
    print(f"    Snippet  : {msg_snippet}")
    if drugs:
        print(f"    Narcotics: {', '.join(drugs)}")
    print("=" * 68 + "\n")

    def _execute():
        # 1. Try plyer if available
        if notification is not None:
            try:
                notification.notify(
                    title=full_title,
                    message=body_text,
                    app_name="DrugShield AI OSINT",
                    timeout=8
                )
                return
            except Exception:
                pass

        # 2. Native Windows PowerShell Toast
        if sys.platform == "win32":
            _show_windows_toast_powershell(full_title, body_text, score)

    if async_call:
        thread = threading.Thread(target=_execute, daemon=True)
        thread.start()
    else:
        _execute()


# Aliases
fire_toast_alert = trigger_threat_popup
notify_threat = trigger_threat_popup

if __name__ == "__main__":
    sample = {
        "platform": "whatsapp_simulation",
        "sender_id": "+91 98765 43210",
        "message_text": "MDMA pure crystal available. Transfer advance to dark_supply@paytm",
        "threat_score": 0.88,
        "extracted_entities": {"narcotics_detected": ["mdma"], "upi_ids": ["dark_supply@paytm"]}
    }
    print("Testing popup_alert.py...")
    trigger_threat_popup(sample, async_call=False)

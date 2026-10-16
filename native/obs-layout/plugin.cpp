// OBS 32 / Qt 6 layout-only helper. No network, platform credentials, or outputs.
// OBS entry points are resolved at runtime so no OBS internals/SDK are copied.
#include <windows.h>
#include <QAction>
#include <QDateTime>
#include <QDir>
#include <QDockWidget>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMainWindow>
#include <QMap>
#include <QPointer>
#include <QSaveFile>
#include <QThread>
#include <QTimer>
#include <QRegularExpression>

namespace {
QPointer<QTimer> timer;
QPointer<QMainWindow> mainWindow;
QString folder, lastRequest, snapshotToken;
QByteArray dockState;
QMap<QString, bool> visibleDocks;
qint64 capturedAt = 0;
bool locked = false;

void respond(const QString &id, bool ok, const QString &token = {})
{
    QJsonObject obj{{"id", id}, {"protocol", 1}, {"ok", ok}, {"token", token}};
    QSaveFile f(folder + "/response.json");
    if (f.open(QIODevice::WriteOnly)) {
        f.write(QJsonDocument(obj).toJson(QJsonDocument::Compact));
        f.commit();
    }
}

void poll()
{
    if (!mainWindow) return;
    QFile f(folder + "/request.json");
    if (!f.open(QIODevice::ReadOnly) || f.size() > 2048) return;
    const auto obj = QJsonDocument::fromJson(f.readAll()).object();
    const QString id = obj["id"].toString();
    static const QRegularExpression nonce("^[a-f0-9]{32}$");
    if (!nonce.match(id).hasMatch() || id == lastRequest) return;
    lastRequest = id;
    const qint64 now = QDateTime::currentMSecsSinceEpoch();
    const double age = now / 1000.0 - obj["at"].toDouble(0);
    if (age < -2 || age > 5) { respond(id, false); return; }
    const QString action = obj["action"].toString();
    if (action == "status") { respond(id, true); return; }
    if (action == "capture") {
        if (!snapshotToken.isEmpty() && now - capturedAt < 120000) {
            respond(id, false); return;
        }
        dockState = mainWindow->saveState();
        visibleDocks.clear();
        for (auto *dock : mainWindow->findChildren<QDockWidget *>()) {
            if (!dock->objectName().isEmpty())
                visibleDocks[dock->objectName()] = !dock->isHidden();
        }
        if (auto *a = mainWindow->findChild<QAction *>("lockDocks")) locked = a->isChecked();
        snapshotToken = id;
        capturedAt = now;
        respond(id, true, id);
        return;
    }
    if (action != "restore" || snapshotToken.isEmpty()
        || obj["token"].toString() != snapshotToken || now - capturedAt > 120000) {
        respond(id, false); return;
    }
    // restoreState includes dock positions/sizes/floating state; it doesn't
    // change the window rectangle, sources, scenes or stream service settings.
    bool ok = mainWindow->restoreState(dockState);
    for (auto *dock : mainWindow->findChildren<QDockWidget *>()) {
        const QString name = dock->objectName();
        if (visibleDocks.contains(name)) {
            dock->setVisible(visibleDocks[name]);
            ok = ok && ((!dock->isHidden()) == visibleDocks[name]);
        } else if (name == "youtubeLiveControlPanel") {
            // A clean temporary profile can recreate this previously absent
            // dock. Do not let it steal space or request another Google login.
            dock->hide();
        }
    }
    if (auto *a = mainWindow->findChild<QAction *>("lockDocks")) a->setChecked(locked);
    if (ok) { snapshotToken.clear(); dockState.clear(); visibleDocks.clear(); }
    respond(id, ok);
}

bool start(QMainWindow *window, const QString &path)
{
    if (!window || path.isEmpty()) return false;
    if (!QDir().mkpath(path)) return false;
    mainWindow = window;
    folder = path;
    // A restarted OBS must not acknowledge an old instance's snapshot.
    QFile::remove(folder + "/response.json");
    lastRequest.clear(); snapshotToken.clear();
    timer = new QTimer(window);
    QObject::connect(timer, &QTimer::timeout, window, poll);
    timer->start(50);
    return true;
}
}

extern "C" __declspec(dllexport) void obs_module_set_pointer(void *) {}
extern "C" __declspec(dllexport) uint32_t obs_module_ver()
{
    using Version = uint32_t (*)();
    auto fn = reinterpret_cast<Version>(GetProcAddress(GetModuleHandleW(L"obs.dll"), "obs_get_version"));
    return fn ? fn() : 0;
}
extern "C" __declspec(dllexport) const char *obs_module_name() { return "Live Desk OBS Layout"; }
extern "C" __declspec(dllexport) const char *obs_module_description() { return "Preserves the operator's dock layout during Live Desk profile reload."; }
extern "C" __declspec(dllexport) const char *obs_module_author() { return "Live Desk"; }
extern "C" __declspec(dllexport) bool obs_module_load()
{
    using Main = void *(*)();
    auto fn = reinterpret_cast<Main>(GetProcAddress(GetModuleHandleW(L"obs-frontend-api.dll"), "obs_frontend_get_main_window"));
    if (!fn) return false;
    auto *window = qobject_cast<QMainWindow *>(static_cast<QObject *>(fn()));
    if (!window) return false;
    const QString path = qEnvironmentVariable("APPDATA") + "/obs-studio/plugin_config/live-desk-layout";
    bool ok = false;
    if (QThread::currentThread() == window->thread()) ok = start(window, path);
    else QMetaObject::invokeMethod(window, [&] { ok = start(window, path); }, Qt::BlockingQueuedConnection);
    return ok;
}
extern "C" __declspec(dllexport) void obs_module_unload()
{
    if (!mainWindow) return;
    auto cleanup = [] { if (timer) { timer->stop(); delete timer; } };
    if (QThread::currentThread() == mainWindow->thread()) cleanup();
    else QMetaObject::invokeMethod(mainWindow, cleanup, Qt::BlockingQueuedConnection);
}

// The GUI regression fixture loads the very same DLL. This export only
// initializes its layout-only timer in a supplied in-process Qt main window.
#ifdef LIVE_DESK_LAYOUT_FIXTURE
extern "C" __declspec(dllexport) bool layout_fixture_start(QMainWindow *window, const char *path)
{ return start(window, QString::fromUtf8(path)); }
#endif

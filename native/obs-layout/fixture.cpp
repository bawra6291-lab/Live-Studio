#include <QApplication>
#include <QAction>
#include <QDateTime>
#include <QDockWidget>
#include <QJsonDocument>
#include <QJsonObject>
#include <QFile>
#include <QLibrary>
#include <QMainWindow>
#include <QSaveFile>
#include <QTemporaryDir>
#include <QThread>
#include <QTextEdit>
#include <QUuid>
#include <QTimer>
#include <stdexcept>
#include <iostream>

extern "C" bool layout_fixture_start(QMainWindow *, const char *);
extern "C" void obs_module_unload();
static void require(bool yes, const char *message) { if (!yes) throw std::runtime_error(message); }
static void settle(int ms = 150) {
    const auto end = QDateTime::currentMSecsSinceEpoch() + ms;
    while (QDateTime::currentMSecsSinceEpoch() < end) {
        QApplication::processEvents(); QThread::msleep(5);
    }
}
static QJsonObject command(const QString &folder, const QString &action,
                           const QString &token = {}, double age = 0) {
    QString id = QUuid::createUuid().toString(QUuid::WithoutBraces).remove('-');
    QJsonObject obj{{"id",id},{"action",action},{"token",token},
                    {"at",QDateTime::currentMSecsSinceEpoch()/1000.0-age}};
    QSaveFile f(folder+"/request.json"); require(f.open(QIODevice::WriteOnly),"request write");
    f.write(QJsonDocument(obj).toJson()); require(f.commit(),"request commit");
    const auto end = QDateTime::currentMSecsSinceEpoch()+3000;
    while (QDateTime::currentMSecsSinceEpoch()<end) {
        settle(10); QFile r(folder+"/response.json");
        if (r.open(QIODevice::ReadOnly)) {
            auto result = QJsonDocument::fromJson(r.readAll()).object();
            if (result["id"].toString()==id) return result;
        }
    }
    throw std::runtime_error("helper response timeout");
}
static QDockWidget *dock(QMainWindow &w, const char *name, Qt::DockWidgetArea area) {
    auto *d = new QDockWidget(name, &w); d->setObjectName(name);
    auto *edit = new QTextEdit(d); edit->setMinimumSize(50,50); d->setWidget(edit);
    w.addDockWidget(area,d); return d;
}
int main(int argc, char **argv) {
    QApplication app(argc,argv);
    try {
        require(argc==2,"pass release DLL path");
        QLibrary binary(QString::fromLocal8Bit(argv[1]));
        require(binary.load(),"release DLL must load with Qt 6");
        require(binary.resolve("obs_module_load") && binary.resolve("obs_module_ver")
                && binary.resolve("obs_module_unload"),"OBS module exports");
        require(!binary.resolve("layout_fixture_start"),"fixture export must not ship");
        QTemporaryDir dir; require(dir.isValid(),"temporary IPC folder");
        QMainWindow w; w.resize(1100,800);
        auto *central = new QTextEdit(&w); central->setMinimumSize(100,100); w.setCentralWidget(central);
        auto *fb = dock(w,"obs-multi-rtmp-dock",Qt::LeftDockWidgetArea);
        auto *scenes = dock(w,"scenesDock",Qt::BottomDockWidgetArea);
        auto *mixer = dock(w,"mixerDock",Qt::BottomDockWidgetArea);
        auto *stats = dock(w,"statsDock",Qt::RightDockWidgetArea);
        auto *youtube = dock(w,"youtubeLiveControlPanel",Qt::RightDockWidgetArea);
        youtube->hide(); stats->hide();
        auto *lock = new QAction(&w); lock->setObjectName("lockDocks"); lock->setCheckable(true); lock->setChecked(true);
        w.show(); settle();
        require(layout_fixture_start(&w,dir.path().toUtf8().constData()),"helper timer starts");
        require(command(dir.path(),"status")["ok"].toBool(),"status acknowledgement");
        const auto beforeSize=w.size(); const auto beforePos=w.pos();
        const QRect fbRect=fb->geometry(), mixerRect=mixer->geometry(), scenesRect=scenes->geometry();
        auto cap=command(dir.path(),"capture"); const auto token=cap["token"].toString();
        require(cap["ok"].toBool() && !token.isEmpty(),"capture confirms snapshot");
        require(!command(dir.path(),"capture")["ok"].toBool(),"cannot overwrite active snapshot");
        // Simulate OBS deleting and recreating the YouTube dock during a clean
        // temporary-profile switch; other panels get rearranged in the process.
        delete youtube;
        youtube=dock(w,"youtubeLiveControlPanel",Qt::RightDockWidgetArea); youtube->show();
        stats->show(); w.addDockWidget(Qt::TopDockWidgetArea,mixer); lock->setChecked(false);
        settle();
        require(!command(dir.path(),"restore","wrong-token")["ok"].toBool(),"invalid token must not restore");
        require(command(dir.path(),"restore",token)["ok"].toBool(),"restore confirms Qt state");
        settle();
        require(youtube->isHidden() && stats->isHidden(),"hidden docks remain hidden");
        require(w.dockWidgetArea(mixer)==Qt::BottomDockWidgetArea,"mixer area restored");
        require(w.dockWidgetArea(fb)==Qt::LeftDockWidgetArea,"FB output dock area restored");
        require(fb->geometry()==fbRect && mixer->geometry()==mixerRect
                && scenes->geometry()==scenesRect,"dock sizes and positions restored");
        require(w.size()==beforeSize && w.pos()==beforePos,"window rectangle unchanged");
        require(lock->isChecked(),"lock preference restored");
        require(!command(dir.path(),"restore",token)["ok"].toBool(),"snapshot cannot replay");
        require(!command(dir.path(),"capture",{},30)["ok"].toBool(),"expired request rejected");
        require(!command(dir.path(),"start-stream")["ok"].toBool(),"arbitrary actions refused");
        // A dock absent at capture must also stay hidden if a profile creates it.
        delete youtube; settle(); cap=command(dir.path(),"capture");
        youtube=dock(w,"youtubeLiveControlPanel",Qt::RightDockWidgetArea); youtube->show(); settle();
        require(command(dir.path(),"restore",cap["token"].toString())["ok"].toBool(),"second restore");
        require(youtube->isHidden(),"new YouTube login dock hidden");
        obs_module_unload();
        std::cout<<"OBS Qt layout fixture passed: docks, geometry, lock, token replay and expiration. No live operations.\n";
        return 0;
    } catch (const std::exception &e) { std::cerr<<e.what()<<"\n"; return 1; }
}

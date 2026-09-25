// walldrift: random popular wallpapers.
//
// This file runs inside Cinnamon, so it stays thin: it keeps time, draws the menu and shows
// notifications. All network, disk and database work happens in the Python backend
// (walldrift/), which runs as its own process and answers with one JSON line on stdout.

const Applet = imports.ui.applet;
const Main = imports.ui.main;
const MessageTray = imports.ui.messageTray;
const PopupMenu = imports.ui.popupMenu;
const Settings = imports.ui.settings;
const ScreenSaver = imports.misc.screenSaver;
const Util = imports.misc.util;
const Gettext = imports.gettext;
const { Gio, GLib, St } = imports.gi;

const UUID = "walldrift@markovic-nikola";
const PYTHON = "/usr/bin/python3";
const ICON = "preferences-desktop-wallpaper";
const TICK_SECONDS = 60;

Gettext.bindtextdomain(UUID, GLib.get_home_dir() + "/.local/share/locale");

function _(text) {
    return Gettext.dgettext(UUID, text);
}

class WalldriftApplet extends Applet.IconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this._dir = metadata.path;
        this._image = null; // the current wallpaper, from the backend's last answer
        this._busy = false; // a backend command is waiting for its answer
        this._pending = null; // a command asked for while busy; runs next
        this._lastAttempt = 0; // when "next" last ran (ms), so a failing change waits a full interval
        this._lastError = null; // don't repeat the same error notification every tick
        this._shownConflicts = new Set(); // warn about each conflict once per session

        this.set_applet_icon_symbolic_name(ICON + "-symbolic");
        this._settings = new Settings.AppletSettings(this, UUID, instanceId);
        this._settingKeys = this._readSettingKeys();
        this._buildMenu(orientation);

        this._screenSaver = new ScreenSaver.ScreenSaverProxy();
        this._screenSaverSignal = this._screenSaver.connectSignal(
            "ActiveChanged",
            (proxy, sender, [active]) => this._onScreenSaverChanged(active)
        );
        this._tick = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, TICK_SECONDS, () => {
            this._onTick();
            return GLib.SOURCE_CONTINUE;
        });

        this._run(this._settings.getValue("change-at-login") ? "next" : "info");
    }

    // Panel events

    on_applet_clicked() {
        this.menu.toggle();
    }

    on_applet_middle_clicked() {
        this._run("next");
    }

    on_applet_removed_from_panel() {
        GLib.source_remove(this._tick);
        this._screenSaver.disconnectSignal(this._screenSaverSignal);
        this._settings.finalize();
    }

    // Menu

    _buildMenu(orientation) {
        this._menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this._menuManager.addMenu(this.menu);

        this._creditItem = this.menu.addAction("", () => this._openPage());
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._nextItem = this.menu.addAction(_("Next wallpaper"), () => this._run("next"));
        this._favItem = this.menu.addAction(_("Save to favorites"), () => this._run("fav"));
        this._banItem = this.menu.addAction(_("Never show this again"), () => this._run("ban"));
        this._updateMenu();
    }

    _updateMenu() {
        const image = this._image;
        const credit = image ? this._credit(image) : _("No wallpaper yet");
        this._creditItem.label.set_text(credit);
        this._creditItem.setSensitive(!!image);
        this._nextItem.setSensitive(!this._busy);
        this._favItem.label.set_text(image && image.favorite ? _("Saved to favorites") : _("Save to favorites"));
        this._favItem.setSensitive(!this._busy && !!image && !image.favorite);
        this._banItem.setSensitive(!this._busy && !!image);
        this.set_applet_tooltip(this._busy ? _("Changing wallpaper…") : credit);
    }

    _credit(image) {
        const page = image.page_url.replace(/^https?:\/\//, "");
        return image.author ? _("Photo by %s").format(image.author) + " · " + page : page;
    }

    _openPage() {
        if (!this._image) return;
        try {
            Gio.AppInfo.launch_default_for_uri(this._image.page_url, null);
        } catch (e) {
            this._notify(_("Could not open %s: %s").format(this._image.page_url, e.message));
        }
    }

    // Timing

    _onTick() {
        if (this._screenSaver.screenSaverActive) return;
        const shownAt = this._image && this._image.shown_at ? this._image.shown_at * 1000 : 0;
        const intervalMs = this._settings.getValue("interval-minutes") * 60 * 1000;
        // Wall-clock time, so a laptop that slept past its change time changes soon after waking.
        // Up to half a tick early counts as due: the change time is recorded just after a tick,
        // so waiting for the full interval would always slip to the following tick.
        const elapsedMs = Date.now() - Math.max(shownAt, this._lastAttempt);
        if (elapsedMs >= intervalMs - (TICK_SECONDS * 1000) / 2) this._run("next");
    }

    _onScreenSaverChanged(active) {
        if (!active && this._settings.getValue("change-on-unlock")) this._run("next");
    }

    // Backend

    _readSettingKeys() {
        // Read once at startup; a small local file, so reading it synchronously is fine.
        const [, bytes] = GLib.file_get_contents(this._dir + "/settings-schema.json");
        const schema = JSON.parse(new TextDecoder().decode(bytes));
        return Object.keys(schema).filter(key => "default" in schema[key]);
    }

    _settingsJson() {
        return JSON.stringify(Object.fromEntries(this._settingKeys.map(key => [key, this._settings.getValue(key)])));
    }

    _run(command) {
        if (this._busy) {
            this._pending = command;
            return;
        }
        this._busy = true;
        if (command === "next") this._lastAttempt = Date.now();
        this._updateMenu();

        let proc;
        try {
            const launcher = new Gio.SubprocessLauncher({
                flags: Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE,
            });
            launcher.set_cwd(this._dir);
            proc = launcher.spawnv([PYTHON, "-m", "walldrift", command]);
        } catch (e) {
            this._onAnswer({ error: _("Could not start %s: %s").format(PYTHON, e.message) });
            return;
        }

        // Settings go on stdin, never in argv, because they hold API keys. They are a few KB,
        // far below a pipe's buffer, so one write sends them all.
        const stdin = proc.get_stdin_pipe();
        const payload = new GLib.Bytes(new TextEncoder().encode(this._settingsJson()));
        stdin.write_bytes_async(payload, GLib.PRIORITY_DEFAULT, null, (stream, result) => {
            try {
                stream.write_bytes_finish(result);
            } catch (e) {
                global.logError(`${UUID}: could not send settings: ${e.message}`);
            }
            stream.close_async(GLib.PRIORITY_DEFAULT, null, (s, r) => s.close_finish(r));
        });

        // The answer is the first line. The backend may keep running afterwards to download
        // more images; that needs nothing from us.
        const stdout = new Gio.DataInputStream({ base_stream: proc.get_stdout_pipe(), close_base_stream: true });
        stdout.read_line_async(GLib.PRIORITY_DEFAULT, null, (stream, result) => {
            let answer = null;
            try {
                const [line] = stream.read_line_finish_utf8(result);
                answer = line ? JSON.parse(line) : null;
            } catch (e) {
                global.logError(`${UUID}: unreadable answer from the backend: ${e.message}`);
            }
            stream.close_async(GLib.PRIORITY_DEFAULT, null, (s, r) => s.close_finish(r));
            if (!answer || typeof answer !== "object") {
                answer = { error: _("The walldrift backend stopped unexpectedly. Details are in ~/.xsession-errors.") };
            }
            this._onAnswer(answer);
        });
    }

    _onAnswer(answer) {
        this._busy = false;
        if (answer.error) {
            if (answer.error !== this._lastError) this._notify(answer.error);
            this._lastError = answer.error;
        } else {
            this._lastError = null;
            this._image = answer.image;
            for (const conflict of answer.conflicts || []) this._warnConflict(conflict);
        }
        this._updateMenu();

        if (this._pending) {
            const command = this._pending;
            this._pending = null;
            this._run(command);
        }
    }

    // Notifications

    _warnConflict(conflict) {
        if (this._shownConflicts.has(conflict.message)) return;
        this._shownConflicts.add(conflict.message);
        this._notify(conflict.message, {
            label: _("Open settings"),
            run: () => Util.spawn(["cinnamon-settings", conflict.settings_module]),
        });
    }

    _notify(body, action) {
        const source = new MessageTray.SystemNotificationSource();
        Main.messageTray.add(source);
        const icon = new St.Icon({ icon_name: ICON, icon_type: St.IconType.FULLCOLOR, icon_size: source.ICON_SIZE });
        const notification = new MessageTray.Notification(source, "walldrift", body, { icon });
        if (action) {
            notification.addButton("action", action.label);
            notification.connect("action-invoked", () => action.run());
        }
        // Keep actionable notices in the tray; let plain errors fade.
        notification.setTransient(!action);
        source.notify(notification);
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new WalldriftApplet(metadata, orientation, panelHeight, instanceId);
}

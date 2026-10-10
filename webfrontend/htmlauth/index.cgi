#!/usr/bin/perl
# LoxBerry-Plugin-Seite fuer LoxPanel – laeuft im LoxBerry-Rahmen (lbheader/
# lbfooter) und LoxBerry-Design (Bootstrap-Klassen).
#  - zeigt den Container-Status
#  - Miniserver-Zugang -> wird an den laufenden Container weitergereicht
#    (POST http://localhost:8098/api/settings/miniserver)
#  - Buttons zur vollen Oberflaeche (/config, /settings) und Container-Steuerung
use strict;
use warnings;
use CGI;
use JSON qw(encode_json decode_json);
use LWP::UserAgent;
use POSIX qw(strftime);
use LoxBerry::System;
use LoxBerry::Web;

my $cgi     = CGI->new;
my $version = LoxBerry::System::pluginversion() // "";
my $api     = "http://localhost:8098";
my $ctl     = "REPLACELBPBINDIR/loxpanel-ctl.sh";
my $log     = "REPLACELBPDATADIR/last_action.log";   # Verlauf der letzten Container-Aktion
my $bdir    = "REPLACELBPDATADIR/backups";           # Konfig-Sicherungen (ueberleben Plugin-Updates)
my $lbhost  = LoxBerry::System::get_localip() // "localhost";
# Lokales Token des Containers: damit darf diese (LoxBerry-geschuetzte) Seite die
# Einstellungs-API auch dann nutzen, wenn die Konfiguration ein Passwort hat.
my $tok = '';
if (open(my $tfh, '<', "REPLACELBPDATADIR/config/.cgi_token")) { local $/; $tok = <$tfh> // ''; close($tfh); }
$tok =~ s/\s+//g;

# HTML-escapen. Texte aus decode_json sind Perl-Zeichenketten (Unicode) - als
# UTF-8-Bytes ausgeben, sonst erscheinen Umlaute (z. B. "Küche") als Zeichensalat.
sub h { my $s = shift; $s = "" unless defined $s; utf8::encode($s) if utf8::is_utf8($s); $s =~ s/&/&amp;/g; $s =~ s/</&lt;/g; $s =~ s/>/&gt;/g; $s =~ s/"/&quot;/g; return $s; }

# Eine Steuer-Aktion nicht-blockierend im Hintergrund starten (Ausgabe -> $log,
# das unten live angezeigt wird). Alle drei Standard-Fds umleiten, damit Apache
# die Anfrage sofort abschliesst (sonst Timeout/Fehler 500 bei laengeren Docker-
# Aktionen). Argumente muessen vorab geprueft/shell-sicher sein.
sub launch_bg {
    my ($label, @args) = @_;
    my $q = join(' ', map { "'$_'" } @args);
    my $sh = "{ date '+[%d.%m %H:%M:%S] $label gestartet'; $q; "
           . "date '+[%d.%m %H:%M:%S] $label abgeschlossen'; } "
           . "> '$log' 2>&1 < /dev/null &";
    system("/bin/bash", "-c", $sh);
}

# LoxBerry-Zugangsdaten robust auslesen: bevorzugt die dekodierte *_RAW-Variante,
# sonst die (moeglicherweise URL-kodierte) Standardvariante selbst dekodieren.
sub _lox_cred {
    my ($raw, $enc) = @_;
    return $raw if defined $raw && $raw ne '';
    $enc = '' unless defined $enc;
    $enc =~ s/\+/ /g;
    $enc =~ s/%([0-9A-Fa-f]{2})/chr(hex($1))/ge;
    return $enc;
}

# Miniserver-Zugang an den Container weiterreichen und Ergebnis-HTML liefern.
sub apply_miniserver {
    my ($data) = @_;
    my $ua = LWP::UserAgent->new(timeout => 25);
    my $r  = $ua->post("$api/api/settings/miniserver", 'X-LoxPanel-Token' => $tok,
        'Content-Type' => 'application/json', Content => encode_json($data));
    if ($r->is_success) {
        my $j = eval { decode_json($r->decoded_content) };
        return "<div class='alert alert-success'>Verbunden &ndash; " . ($j->{nControls} // 0) . " Controls geladen.</div>"
            if $j && $j->{ok};
        return "<div class='alert alert-danger'>Fehler: " . h($j ? ($j->{error} // 'unbekannt') : 'ungueltige Antwort') . "</div>";
    }
    return "<div class='alert alert-danger'>Container nicht erreichbar &ndash; l&auml;uft er? (unten &bdquo;Starten&ldquo;)</div>";
}

# Android-Panel (Shelly Wall Display u.a.) per adb einrichten: der Container
# installiert den LoxPanel-Launcher und traegt diese LoxBerry-Adresse ein.
sub setup_panel {
    my ($ip, $panel, $device) = @_;
    my $ua = LWP::UserAgent->new(timeout => 180);   # Installation per WLAN kann dauern
    my $r  = $ua->post("$api/api/panel/launcher", 'X-LoxPanel-Token' => $tok, 'Content-Type' => 'application/json',
        Content => encode_json({ ip => $ip, panel => $panel, device => $device, server => "$lbhost:8098" }));
    return "<div class='alert alert-danger'>Container nicht erreichbar &ndash; l&auml;uft er?</div>"
        unless $r->is_success || $r->code == 400;
    my $j = eval { decode_json($r->decoded_content) };
    return "<div class='alert alert-danger'>Ung&uuml;ltige Antwort vom Container.</div>" unless $j;
    my $steps = join('', map {
        "<li>" . ($_->{ok} ? "&#10004;" : "&#10008;") . " " . h($_->{step})
        . ($_->{out} ne '' ? " <small style='color:#777'>" . h($_->{out}) . "</small>" : "") . "</li>"
    } @{ $j->{steps} // [] });
    my $list = $steps ? "<ul style='margin:8px 0 0;padding-left:18px'>$steps</ul>" : "";
    my $nofully = ($j->{ok} && !$j->{fully})
        ? "<br><b>Fully Kiosk fehlt noch</b> &ndash; bitte von <a href='https://www.fully-kiosk.com' target='_blank'>fully-kiosk.com</a> "
          . "auf dem Panel installieren, danach das tilebert-Symbol antippen." : "";
    return "<div class='alert " . ($nofully ? "alert-warning" : "alert-success") . "'>Launcher eingerichtet &ndash; "
         . "das tilebert-Symbol &ouml;ffnet " . h($j->{url}) . " in Fully Kiosk.$nofully$list</div>" if $j->{ok};
    return "<div class='alert alert-danger'>" . h($j->{error} // 'Fehler') . "$list</div>";
}

# ---- Backup herunterladen (GET ?download=<datei>) - vor jeder anderen Ausgabe ----
if (defined(my $dl = $cgi->param('download'))) {
    $dl =~ s{.*[\\/]}{};
    if ($dl =~ /^loxpanelfav-config-[\w.\-]+\.tar\.gz$/ && -f "$bdir/$dl" && open(my $fh, '<:raw', "$bdir/$dl")) {
        binmode STDOUT;
        print "Content-Type: application/gzip\r\nContent-Disposition: attachment; filename=\"$dl\"\r\n"
            . "Content-Length: " . (-s "$bdir/$dl") . "\r\n\r\n";
        local $/ = \65536;
        while (my $chunk = <$fh>) { print $chunk; }
        close $fh;
    } else {
        print "Status: 404 Not Found\r\nContent-Type: text/plain\r\n\r\nBackup nicht gefunden.\n";
    }
    exit 0;
}

# ---- POST verarbeiten (vor jeder Ausgabe) ----
my $msg = "";
my $refresh = 0;   # nach einer Aktion die Seite per GET nachladen (Live-Verlauf)
my $action = $cgi->param('action') // '';

if ($action eq 'miniserver') {
    $msg = apply_miniserver({
        host       => scalar($cgi->param('host')) // '',
        user       => scalar($cgi->param('user')) // '',
        pass       => scalar($cgi->param('pass')) // '',
        port       => int((scalar($cgi->param('port')) || 443)),
        verify_tls => ($cgi->param('tls') ? JSON::true : JSON::false),
    });
}
elsif ($action eq 'fromlox') {
    # Miniserver-Zugang aus der zentralen LoxBerry-Konfiguration uebernehmen
    # (erster/niedrigster Miniserver). Admin_RAW/Pass_RAW sind die dekodierten
    # Zugangsdaten.
    my %ms = LoxBerry::System::get_miniservers();
    my $m;
    for my $k (sort { $a <=> $b } keys %ms) { $m = $ms{$k}; last; }
    if ($m && ($m->{IPAddress} // '') ne '') {
        $msg = apply_miniserver({
            host       => $m->{IPAddress},
            user       => _lox_cred($m->{Admin_RAW}, $m->{Admin}),
            pass       => _lox_cred($m->{Pass_RAW},  $m->{Pass}),
            port       => int($m->{Port} || 443),   # LoxBerry-Port spiegeln (80=Gen1/HTTP, 443=Gen2/HTTPS)
            verify_tls => JSON::false,
        });
    } else {
        $msg = "<div class='alert alert-danger'>In LoxBerry ist kein Miniserver konfiguriert (Hauptmen&uuml; &rarr; Miniserver).</div>";
    }
}
elsif ($action eq 'panelsetup') {
    my $ip    = scalar($cgi->param('panelip')) // '';
    my $panel = scalar($cgi->param('panelid')) // '';
    my $dev   = (scalar($cgi->param('paneldev')) // '') eq 'android' ? 'android' : 'shelly';
    $ip =~ s/^\s+|\s+$//g;
    $msg = setup_panel($ip, $panel, $dev);
}
elsif ($action =~ /^(start|stop|restart)$/) {
    my $act = $1;   # durch Regex begrenzt -> shell-sicher
    launch_bg("Aktion \"$act\"", $ctl, $act);
    $msg = "<div class='alert alert-info'>Aktion &bdquo;$act&ldquo; l&auml;uft &hellip; "
         . "der Start kann 1&ndash;2&nbsp;Min dauern. "
         . "Der Verlauf erscheint unten unter &bdquo;Letzte Aktion&ldquo; und aktualisiert sich automatisch.</div>";
    $refresh = 1;
}
elsif ($action eq 'resetpw') {
    launch_bg("Passwort zuruecksetzen", $ctl, "resetpw");
    $msg = "<div class='alert alert-info'>Passwortschutz der Konfiguration wird entfernt &hellip; Ergebnis unten unter &bdquo;Letzte Aktion&ldquo;.</div>";
    $refresh = 1;
}
elsif ($action eq 'backup') {
    launch_bg("Backup", $ctl, "backup");
    $msg = "<div class='alert alert-info'>Backup wird erstellt &hellip; Ergebnis unten unter &bdquo;Letzte Aktion&ldquo;.</div>";
    $refresh = 1;
}
elsif ($action eq 'restore') {
    my $file = scalar($cgi->param('file')) // '';
    $file =~ s{.*[\\/]}{};   # nur Basename, keine Pfad-Tricks
    if ($file =~ /^loxpanelfav-config-[\w.\-]+\.tar\.gz$/ && -f "$bdir/$file") {
        launch_bg("Wiederherstellen ($file)", $ctl, "restore", $file);
        $msg = "<div class='alert alert-info'>Wiederherstellung l&auml;uft &hellip; das Panel startet dabei neu. Verlauf unten.</div>";
        $refresh = 1;
    } else {
        $msg = "<div class='alert alert-danger'>Ung&uuml;ltiger oder unbekannter Backup-Name.</div>";
    }
}
elsif ($action eq 'upload_backup') {
    # Gesicherte Konfiguration (vom PC) wieder hochladen -> erscheint in der Liste
    my $fh = $cgi->upload('bfile');
    my $orig = scalar($cgi->param('bfile')) // '';
    if (!$fh) {
        $msg = "<div class='alert alert-danger'>Keine Datei ausgew&auml;hlt.</div>";
    } else {
        binmode $fh;
        my $data = do { local $/; <$fh> } // '';
        if (length($data) < 20 || substr($data, 0, 2) ne "\x1f\x8b") {
            $msg = "<div class='alert alert-danger'>Keine tilebert-Sicherung (.tar.gz) &ndash; Datei verworfen.</div>";
        } elsif (length($data) > 50 * 1024 * 1024) {
            $msg = "<div class='alert alert-danger'>Datei zu gro&szlig; (max. 50 MB).</div>";
        } else {
            mkdir $bdir unless -d $bdir;
            my $ts = strftime("%Y%m%d-%H%M%S", localtime);
            my $name = "loxpanelfav-config-$ts-upload.tar.gz";
            if (open(my $out, '>:raw', "$bdir/$name")) {
                print $out $data; close $out;
                $msg = "<div class='alert alert-success'>Sicherung hochgeladen: " . h($name) . " &ndash; mit &bdquo;Wiederherstellen&ldquo; einspielen.</div>";
            } else {
                $msg = "<div class='alert alert-danger'>Speichern fehlgeschlagen.</div>";
            }
        }
    }
}
elsif ($action eq 'delete_backup') {
    my $file = scalar($cgi->param('file')) // '';
    $file =~ s{.*[\\/]}{};
    if ($file =~ /^loxpanelfav-config-[\w.\-]+\.tar\.gz$/ && -f "$bdir/$file") {
        unlink "$bdir/$file";
        $msg = "<div class='alert alert-success'>Backup gel&ouml;scht: " . h($file) . "</div>";
    } else {
        $msg = "<div class='alert alert-danger'>Backup nicht gefunden.</div>";
    }
}

# ---- Status vom Container holen ----
my ($running, $conn, $mhost, $muser, $mport, $haspass) = (0, 0, '', '', 443, 0);
my $sr = LWP::UserAgent->new(timeout => 5)->get("$api/api/settings", 'X-LoxPanel-Token' => $tok);
if ($sr->is_success) {
    $running = 1;
    my $j = eval { decode_json($sr->decoded_content) };
    if ($j) {
        $conn = $j->{connected} ? 1 : 0;
        my $m = $j->{miniserver} // {};
        $mhost = $m->{host} // ''; $muser = $m->{user} // '';
        $mport = $m->{port} // 443; $haspass = $m->{hasPass} ? 1 : 0;
    }
}
# Laufender Code-Stand (Version/Commit) fuer die Statuskachel
my ($av, $ac) = ($version, '');
if ($running) {
    my $vr = LWP::UserAgent->new(timeout => 4)->get("$api/api/version");
    if ($vr->is_success) { my $vj = eval { decode_json($vr->decoded_content) };
        if ($vj) { $av = $vj->{version} // $av; $ac = substr($vj->{commit} // '', 0, 7); } }
}
my $repo = "https://github.com/actionhero-zz/loxohnepanel";
# Panel-Profile fuer die Auswahl "Web-App oeffnen" (id -> Titel)
my @plist;
if ($running) {
    my $pr = LWP::UserAgent->new(timeout => 6)->get("$api/api/meta", 'X-LoxPanel-Token' => $tok);
    if ($pr->is_success) { my $pj = eval { decode_json($pr->decoded_content) };
        if ($pj && ref $pj->{panels} eq 'HASH') {
            for my $id (sort keys %{ $pj->{panels} }) {
                next if $id =~ /^__/;
                my $t = (ref $pj->{panels}{$id} eq 'HASH' ? $pj->{panels}{$id}{title} : '') || $id;
                push @plist, [$id, $t];
            } } }
}
my $popts = join('', map { "<option value='" . h($_->[0]) . "'>" . h($_->[1]) . "</option>" } @plist)
    || "<option value=''>Standard</option>";
my $stat = !$running ? "<span style='color:#a94442'>Container l&auml;uft nicht</span>"
    : $conn ? "<span style='color:#3c763d'>l&auml;uft &middot; Miniserver verbunden</span>"
    : "<span style='color:#8a6d3b'>l&auml;uft &middot; noch kein Miniserver</span>";

my ($hh, $hu, $hp) = (h($mhost), h($muser), h($mport));
my $passph = $haspass ? "unver&auml;ndert lassen" : "Passwort eingeben";

# ---- Verlauf der letzten Aktion (Tail) ----
my ($logtail, $busy) = ("", 0);
if (open(my $lf, '<', $log)) {
    my @lines = <$lf>;
    close $lf;
    # "busy", solange die Abschluss-Zeile noch fehlt -> Seite pollt dann weiter.
    my $last = @lines ? $lines[-1] : '';
    $busy = ($last !~ /abgeschlossen/) ? 1 : 0;
    @lines = splice(@lines, -25) if @lines > 25;
    $logtail = h(join('', @lines));
}
# Waehrend eine Aktion laeuft (frisch angestossen ODER Log noch offen) die Seite
# per GET nachladen (kein erneutes POST -> keine Doppel-Aktion).
my $poll = ($refresh || $busy) ? 1 : 0;
my $refresh_html = $poll
    ? "<script>setTimeout(function(){location.replace(location.pathname);},4000);</script>"
    : "";

my $log_html = "";
if ($logtail ne "") {
    my $spin = $busy ? " &middot; l&auml;uft&hellip;" : "";
    $log_html = <<"LOGH";
<section class="lpx-card lpx-wide">
  <div class="lpx-h"><h3>Letzte Aktion$spin</h3>
    <a class="lpx-btn lpx-ghost lpx-sm" href="#" data-role="none" data-ajax="false" onclick="location.replace(location.pathname);return false;">Aktualisieren</a></div>
  <pre class="lpx-log">$logtail</pre>
</section>
LOGH
}

# ---- Vorhandene Backups auflisten (neueste zuerst) ----
my @backups;
if (opendir(my $dh, $bdir)) {
    @backups = sort { $b cmp $a }
               grep { /^loxpanelfav-config-.*\.tar\.gz$/ } readdir($dh);
    closedir($dh);
}
my $blist = "";
for my $b (@backups) {
    my @st  = stat("$bdir/$b");
    my $kb  = @st ? int(($st[7] + 1023) / 1024) : 0;
    my $when= @st ? strftime("%d.%m.%Y %H:%M", localtime($st[9])) : "";
    my $hb  = h($b);
    $blist .= "<tr>"
        . "<td class='lpx-mono'>$hb</td>"
        . "<td class='lpx-mut'>$when</td>"
        . "<td class='lpx-mut'>${kb}&nbsp;KB</td>"
        . "<td class='lpx-act'>"
          . "<form method='post' style='display:inline;margin:0' "
          . "onsubmit=\"return confirm('Diesen Stand wiederherstellen? Die aktuellen Panels werden ersetzt (der jetzige Stand wird vorher automatisch gesichert). Das Panel startet neu.');\">"
          . "<input type='hidden' name='action' value='restore'>"
          . "<input type='hidden' name='file' value='$hb'>"
          . "<button class='lpx-btn lpx-sec lpx-sm' data-role='none' type='submit'>Wiederherstellen</button></form> "
          . "<a class='lpx-btn lpx-sec lpx-sm' data-role='none' data-ajax='false' href='?download=$hb' title='Herunterladen'>&#8615;</a> "
          . "<form method='post' style='display:inline;margin:0' "
          . "onsubmit=\"return confirm('Dieses Backup l&#246;schen?');\">"
          . "<input type='hidden' name='action' value='delete_backup'>"
          . "<input type='hidden' name='file' value='$hb'>"
          . "<button class='lpx-x' data-role='none' type='submit' title='Backup l&ouml;schen' aria-label='Backup l&ouml;schen'>&#215;</button></form>"
        . "</td></tr>";
}
my $backups_html = $blist
    ? "<div class='lpx-tbl'><table><tr><th>Datei</th><th>Datum</th><th>Gr&ouml;&szlig;e</th><th></th></tr>$blist</table></div>"
    : "<p class='lpx-note'>Noch keine Sicherung vorhanden.</p>";

# ---- Ausgabe im LoxBerry-Rahmen ----
LoxBerry::Web::lbheader("tilebert V$version", $repo, "");

# Status-Kacheln (Punkte als viereckige Pillen, Farben wie im Panel)
my ($cst, $ccl) = $running ? ("l&auml;uft", "ok") : ("gestoppt", "bad");
my ($mst, $mcl) = !$running ? ("&ndash;", "off") : $conn ? ("verbunden", "ok") : ("nicht verbunden", "warn");
my $msub = ($running && $mhost ne '') ? $hh : "noch nicht eingerichtet";
my $ver_html = h($av) . ($ac ne '' ? " <small>&middot; $ac</small>" : "");
my $nb = scalar(@backups);
my $bcl = $nb ? "ok" : "off";
my $bsub = "noch keine";
if ($nb) { (my $n = $backups[0]) =~ s/^loxpanelfav-config-//; $n =~ s/\.tar\.gz$//; $bsub = "neueste: " . h($n); }

print <<"HTML";
<style>
  .lpx{--lpx-g:#6dac20;--lpx-gd:#5a9419;--lpx-acc:#f3d27a;--lpx-ink:#1f2430;--lpx-mut:#6b7280;--lpx-line:#e4e7ec;
    --lpx-bg:#f6f7f9;--lpx-ok:#52b881;--lpx-warn:#e9b949;--lpx-bad:#e2695f;
    font-family:inherit;color:var(--lpx-ink);max-width:1180px;margin:0 auto;padding:4px 0 24px;}
  .lpx,.lpx *{box-sizing:border-box;text-shadow:none !important;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;letter-spacing:normal;}
  .lpx code,.lpx pre,.lpx .lpx-mono{font-family:ui-monospace,Menlo,Consolas,monospace;}
  .lpx b,.lpx strong{font-weight:700;} .lpx p{margin:0;}
  .lpx-open{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.08);border-radius:999px;padding:4px 4px 4px 6px;}
  .lpx-sel{height:32px;border:0;border-radius:999px;padding:0 28px 0 12px;font-size:13px;font-weight:600;color:#fff;cursor:pointer;
    background:rgba(255,255,255,.12) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23fff' stroke-width='1.6' fill='none'/%3E%3C/svg%3E") no-repeat right 11px center;
    -webkit-appearance:none;appearance:none;max-width:180px;}
  .lpx-sel option{color:#1f2430;}
  .lpx-open .lpx-btn{height:32px;}
  .lpx h3{margin:0;font-size:16px;line-height:1.3;font-weight:700;color:var(--lpx-ink);}
  .lpx-hero{position:relative;overflow:hidden;border-radius:20px;padding:22px 24px;margin-bottom:16px;
    background:linear-gradient(135deg,#232838 0%,#2d3448 60%,#38405a 100%);color:#fff;box-shadow:0 10px 30px rgba(31,36,48,.18);}
  .lpx-hero::after{content:"";position:absolute;right:-80px;bottom:-110px;width:240px;height:240px;border-radius:60px;transform:rotate(18deg);
    background:var(--lpx-acc);opacity:.16;}
  .lpx-top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;position:relative;z-index:1;}
  .lpx-brand{display:flex;align-items:center;gap:12px;}
  .lpx-logo{width:42px;height:42px;border-radius:13px;background:var(--lpx-acc);display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:8px;}
  .lpx-logo i{background:#232838;border-radius:3px;opacity:.85;} .lpx-logo i:nth-child(2){opacity:.45;}
  .lpx-brand b{display:block;font-size:20px;letter-spacing:.2px;} .lpx-brand span{font-size:12.5px;color:#c9cfdb;}
  .lpx-ver{color:#fff !important;text-decoration:none !important;background:rgba(255,255,255,.12);border-radius:999px;padding:6px 14px;font-size:13px;font-weight:600;}
  .lpx-ver small{color:#c9cfdb;font-weight:400;} .lpx-ver:hover{background:rgba(255,255,255,.2);}
  .lpx-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:18px;position:relative;z-index:1;}
  .lpx-stat{background:rgba(255,255,255,.08);border-radius:14px;padding:12px 14px;}
  .lpx-stat .k{font-size:11px;letter-spacing:.6px;text-transform:uppercase;color:#aab2c2;}
  .lpx-stat .v{display:flex;align-items:center;gap:8px;font-size:16px;font-weight:700;margin-top:4px;}
  .lpx-stat .s{font-size:12px;color:#c9cfdb;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .lpx-dot{width:10px;height:10px;border-radius:32%;flex:none;background:#8a93a3;}
  .lpx-dot.ok{background:var(--lpx-ok);box-shadow:0 0 0 3px rgba(82,184,129,.25);} .lpx-dot.warn{background:var(--lpx-warn);} .lpx-dot.bad{background:var(--lpx-bad);}
  .lpx-go{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;position:relative;z-index:1;}
  .lpx-msg:empty{display:none;} .lpx-msg{margin-bottom:16px;} .lpx-msg .alert{border-radius:14px;margin:0;}
  .lpx-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start;}
  .lpx-card{background:#fff;border:1px solid var(--lpx-line);border-radius:16px;padding:18px 20px;box-shadow:0 2px 10px rgba(31,36,48,.04);}
  .lpx-wide{grid-column:1/-1;margin-top:16px;}
  .lpx-h{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;}
  .lpx-h small{color:var(--lpx-mut);font-weight:400;font-size:12.5px;}
  .lpx-note{color:var(--lpx-mut);font-size:13px;line-height:1.5;margin:0 0 12px;}
  .lpx-f{display:grid;grid-template-columns:minmax(0,2fr) minmax(70px,.7fr);gap:10px;}
  .lpx-f2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px;}
  .lpx label.l{display:block;font-size:12px;font-weight:600;color:var(--lpx-mut);margin:0 0 4px;}
  .lpx input.i{width:100%;height:40px;border:1px solid var(--lpx-line);border-radius:10px;padding:0 12px;font:inherit;font-size:14px;background:var(--lpx-bg);color:var(--lpx-ink);}
  .lpx input.i:focus{outline:none;border-color:var(--lpx-g);box-shadow:0 0 0 3px rgba(109,172,32,.18);background:#fff;}
  .lpx-chk{display:flex;align-items:center;gap:8px;font-size:13px;margin:12px 0 2px;color:var(--lpx-ink);font-weight:400;}
  .lpx-chk input{width:16px;height:16px;accent-color:var(--lpx-g);margin:0;}
  .lpx-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;} .lpx-row form{margin:0;display:contents;}
  .lpx-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:40px;padding:0 20px;border-radius:999px;border:1px solid transparent;
    font:inherit;font-size:14px;font-weight:600;cursor:pointer;text-decoration:none !important;white-space:nowrap;transition:background .15s,transform .1s;}
  .lpx-btn:active{transform:scale(.98);}
  .lpx-pri{background:var(--lpx-g);color:#fff !important;} .lpx-pri:hover{background:var(--lpx-gd);}
  .lpx-acc{background:var(--lpx-acc);color:#2a2208 !important;} .lpx-acc:hover{filter:brightness(.96);}
  .lpx-sec{background:#fff;color:var(--lpx-ink) !important;border-color:var(--lpx-line);} .lpx-sec:hover{background:var(--lpx-bg);}
  .lpx-ghost{background:rgba(255,255,255,.12);color:#fff !important;} .lpx-ghost:hover{background:rgba(255,255,255,.2);}
  .lpx-card .lpx-ghost{background:var(--lpx-bg);color:var(--lpx-ink) !important;}
  .lpx-warnbtn{background:#fff;color:#b5443b !important;border-color:#f0c4c0;} .lpx-warnbtn:hover{background:#fdf1f0;}
  .lpx-sm{height:32px;padding:0 14px;font-size:13px;}
  .lpx-sep{height:1px;background:var(--lpx-line);margin:16px 0;}
  .lpx-tbl{overflow-x:auto;margin-top:4px;} .lpx-tbl table{width:100%;border-collapse:collapse;font-size:13px;}
  .lpx-tbl th{text-align:left;font-size:11px;letter-spacing:.5px;text-transform:uppercase;color:var(--lpx-mut);font-weight:600;padding:6px 8px;}
  .lpx-tbl td{padding:7px 8px;border-top:1px solid var(--lpx-line);vertical-align:middle;}
  .lpx-mono{font-family:ui-monospace,Menlo,monospace;font-size:12px;word-break:break-all;} .lpx-mut{color:var(--lpx-mut);white-space:nowrap;}
  .lpx-act{white-space:nowrap;text-align:right;} .lpx-act form{display:inline;margin:0;}
  .lpx-x{width:30px;height:30px;border-radius:32%;border:1px solid var(--lpx-line);background:#fff;color:var(--lpx-mut);cursor:pointer;font-size:16px;line-height:1;vertical-align:middle;}
  .lpx-x:hover{color:#b5443b;border-color:#f0c4c0;background:#fdf1f0;}
  .lpx-log{max-height:260px;overflow:auto;background:#1e2230;color:#d6dae3;padding:12px 14px;border-radius:12px;font-size:12px;line-height:1.5;white-space:pre-wrap;margin:0;border:0;}
  \@media (max-width:760px){ .lpx-grid{grid-template-columns:1fr;} }
  \@media (max-width:560px){ .lpx-hero{padding:18px;} .lpx-f,.lpx-f2{grid-template-columns:1fr;} .lpx-btn{flex:1 1 auto;} }
</style>
<div class="lpx">
  <section class="lpx-hero">
    <div class="lpx-top">
      <div class="lpx-brand"><div class="lpx-logo" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
        <div><b>tilebert</b><span>ein LoxPanel Fork von Lenardo1 &ndash; Wandpanels, Tablets &amp; Handy f&uuml;r Loxone</span></div></div>
      <a class="lpx-ver" href="$repo" target="_blank" rel="noopener" title="GitHub-Repository &ouml;ffnen">V $ver_html</a>
    </div>
    <div class="lpx-stats">
      <div class="lpx-stat"><div class="k">Container</div><div class="v"><i class="lpx-dot $ccl"></i>$cst</div><div class="s">Port 8098</div></div>
      <div class="lpx-stat"><div class="k">Miniserver</div><div class="v"><i class="lpx-dot $mcl"></i>$mst</div><div class="s">$msub</div></div>
      <div class="lpx-stat"><div class="k">Sicherungen</div><div class="v"><i class="lpx-dot $bcl"></i>$nb</div><div class="s">$bsub</div></div>
    </div>
    <div class="lpx-go">
      <a class="lpx-btn lpx-acc" href="http://$lbhost:8098/config" target="_blank" rel="noopener" data-role="none">Konfiguration &ouml;ffnen</a>
      <span class="lpx-open">
        <select id="lpx_panel" class="lpx-sel" data-role="none" aria-label="Panel">$popts</select>
        <a class="lpx-btn lpx-ghost" href="http://$lbhost:8098/" target="_blank" rel="noopener" data-role="none"
           onclick="var v=document.getElementById('lpx_panel').value;this.href='http://$lbhost:8098/'+(v?'?panel='+encodeURIComponent(v):'');">Web-App &ouml;ffnen</a>
      </span>
    </div>
  </section>

  <div class="lpx-msg">$msg</div>

  <div class="lpx-grid">
    <section class="lpx-card">
      <div class="lpx-h"><h3>Miniserver-Zugang</h3></div>
      <form method="post" id="msform" data-ajax="false">
        <input type="hidden" name="action" value="miniserver">
        <div class="lpx-f">
          <div><label class="l">Host / IP</label><input class="i" data-role="none" name="host" value="$hh" placeholder="192.168.1.50"></div>
          <div><label class="l">Port</label><input class="i" data-role="none" name="port" value="$hp"></div>
        </div>
        <div class="lpx-f2">
          <div><label class="l">Benutzer</label><input class="i" data-role="none" name="user" value="$hu" autocomplete="off"></div>
          <div><label class="l">Passwort</label><input class="i" data-role="none" type="password" name="pass" placeholder="$passph" autocomplete="new-password"></div>
        </div>
        <label class="lpx-chk"><input type="checkbox" data-role="none" name="tls"> Zertifikat pr&uuml;fen (Gen2 selbstsigniert: aus)</label>
        <p class="lpx-note" style="margin:6px 0 0">Port 443 = HTTPS (Gen2), Port 80 = HTTP (Gen1).</p>
      </form>
      <div class="lpx-row">
        <button class="lpx-btn lpx-pri" data-role="none" type="submit" form="msform">Verbinden &amp; Speichern</button>
        <form method="post" data-ajax="false"><input type="hidden" name="action" value="fromlox"><button class="lpx-btn lpx-sec" data-role="none" type="submit">Aus LoxBerry &uuml;bernehmen</button></form>
      </div>
    </section>

    <section class="lpx-card">
      <div class="lpx-h"><h3>Container</h3></div>
      <p class="lpx-note">Updates installierst du &uuml;ber die <b>LoxBerry-Pluginverwaltung</b> &ndash; LoxBerry f&uuml;hrt. Hier nur Start, Stopp und Neustart (z.&nbsp;B. nach einem H&auml;nger).</p>
      <div class="lpx-row">
        <form method="post" data-ajax="false"><input type="hidden" name="action" value="restart"><button class="lpx-btn lpx-pri" data-role="none" type="submit">Neu starten</button></form>
        <form method="post" data-ajax="false"><input type="hidden" name="action" value="start"><button class="lpx-btn lpx-sec" data-role="none" type="submit">Starten</button></form>
        <form method="post" data-ajax="false"><input type="hidden" name="action" value="stop"><button class="lpx-btn lpx-sec" data-role="none" type="submit">Stoppen</button></form>
      </div>
      <div class="lpx-sep"></div>
      <div class="lpx-h" style="margin-bottom:6px"><h3>Passwort vergessen?</h3></div>
      <p class="lpx-note">Entfernt den Passwortschutz der Konfiguration &ndash; danach dort ein neues setzen.</p>
      <form method="post" data-ajax="false" onsubmit="return confirm('Passwortschutz der Konfiguration entfernen?')"><input type="hidden" name="action" value="resetpw"><button class="lpx-btn lpx-warnbtn" data-role="none" type="submit">Passwort zur&uuml;cksetzen</button></form>
    </section>

    <section class="lpx-card lpx-wide" style="margin-top:0">
      <div class="lpx-h"><h3>Sichern &amp; Wiederherstellen <small>&middot; die letzten 20 bleiben, auch bei Updates</small></h3>
        <form method="post" data-ajax="false" style="margin:0"><input type="hidden" name="action" value="backup"><button class="lpx-btn lpx-pri lpx-sm" data-role="none" type="submit">Backup jetzt erstellen</button></form></div>
      <p class="lpx-note">Panels, Kacheln, Design und Miniserver-Zugang als Archiv unter <code>$bdir</code>. Sicherungen bleiben bei Plugin-Updates erhalten; mit &#8615; auf den PC laden, unten wieder hochladen.</p>
      $backups_html
      <form method="post" enctype="multipart/form-data" data-ajax="false" class="lpx-row" style="align-items:center">
        <input type="hidden" name="action" value="upload_backup">
        <input type="file" name="bfile" accept=".gz,application/gzip" data-role="none" required style="font-size:13px">
        <button class="lpx-btn lpx-sec lpx-sm" data-role="none" type="submit">Sicherung hochladen</button>
      </form>
    </section>
  </div>
$log_html
</div>
$refresh_html
HTML

LoxBerry::Web::lbfooter();

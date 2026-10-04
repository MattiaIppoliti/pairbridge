"""Apply our small UI guard to an exact third-party input, then build locally."""
from pathlib import Path
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from .container import write_json
from .profile import ROOT, PROFILE, checked_bytes

ANDROID = '{http://schemas.android.com/apk/res/android}'
APP = 'smali/com/airoha/utapp/sdk/'


def tool(name):
    java_home = os.environ.get('JAVA_HOME')
    if name in ['java', 'keytool', 'jarsigner'] and java_home and (Path(java_home) / 'bin' / name).is_file():
        return str(Path(java_home) / 'bin' / name)
    found = shutil.which(name)
    if found:
        return found
    raise ValueError(f'Missing tool: {name}. See docs/BUILD.md')


def run(args, env=None):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, env=env)
    if result.returncode:
        raise ValueError(f'{Path(str(args[0])).name} failed: {(result.stdout + result.stderr)[-1600:]}')
    return result.stdout + result.stderr


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('The decoded source does not match the reviewed patch location')
    return text.replace(before, after, 1)


def sdk_fingerprint(decoded):
    files = list((decoded / 'smali/com/airoha/libfota1562').rglob('*.smali'))
    files += list((decoded / 'smali/com/airoha/sdk').glob('AB1562FotaControl*.smali'))
    files = [p for p in files if p.name != 'PairBridgeGuard.smali']
    if len(files) != 127:
        raise ValueError('Unexpected SDK FOTA class count')
    # The assembler can change line/debug annotations; compare meaningful smali.
    result = {}
    for path in files:
        code = '\n'.join(line.strip() for line in path.read_text().splitlines()
                         if line.strip() and not line.lstrip().startswith(('#', '.line ', '.source ')))
        result[path.relative_to(decoded).as_posix()] = hashlib.sha256(code.encode()).hexdigest()
    return result


def patch_decoded(decoded):
    decoded = Path(decoded)
    cfg = PROFILE['app']
    manifest_path = decoded / 'AndroidManifest.xml'
    text = manifest_path.read_text()
    manifest = ET.fromstring(text)
    app = manifest.find('application')
    if manifest.get('package') != cfg['source_package'] or app is None or app.get(ANDROID + 'debuggable') != 'false':
        raise ValueError('Unexpected manifest/package/debug configuration')
    original_permissions = {p.get(ANDROID + 'name') for p in manifest.findall('uses-permission')}
    if 'android.permission.INTERNET' in original_permissions:
        raise ValueError('Unexpected Internet permission')
    original_sdk = sdk_fingerprint(decoded)
    text = once(text, 'package="' + cfg['source_package'] + '"', 'package="' + cfg['output_package'] + '"')
    text = once(text, 'android:authorities="' + cfg['source_package'] + '.provider"',
                'android:authorities="' + cfg['output_package'] + '.provider"')
    manifest_path.write_text(text)
    p = decoded / 'res/values/strings.xml'
    strings, count = re.subn(r'<string name="app_name">[^<]*</string>', '<string name="app_name">PairBridge</string>', p.read_text())
    if count != 1:
        raise ValueError('Unexpected application label resource')
    p.write_text(strings)
    guard = (ROOT / 'android/guard.smali').read_text().replace('@FIRMWARE_VERSION@', cfg['runtime_version']).replace('@FLASH_SIZE@', cfg['runtime_flash'])
    (decoded / 'smali/com/airoha/libfota1562/PairBridgeGuard.smali').write_text(guard)
    p = decoded / (APP + 'TwsFota1562Fragment.smali')
    p.write_text(p.read_text() + '\n' + (ROOT / 'android/fragment-methods.smali').read_text())
    p = decoded / (APP + 'TwsFota1562Fragment$11.smali')
    start = '.method public onClick(Landroid/view/View;)V\n    .locals 3\n'
    s = once(p.read_text(), start, start + '''
    iget-object v0, p0, Lcom/airoha/utapp/sdk/TwsFota1562Fragment$11;->this$0:Lcom/airoha/utapp/sdk/TwsFota1562Fragment;
    invoke-static {v0}, Lcom/airoha/utapp/sdk/TwsFota1562Fragment;->pairBridgeReady(Lcom/airoha/utapp/sdk/TwsFota1562Fragment;)Z
    move-result v0
    if-nez v0, :pairbridge_ready
    return-void
    :pairbridge_ready
''')
    call = '    invoke-interface {p1, v0}, Lcom/airoha/sdk/api/ota/AirohaFOTAControl;->applyNewFirmware(I)Z'
    s = once(s, call, '''    iget-object v1, p0, Lcom/airoha/utapp/sdk/TwsFota1562Fragment$11;->this$0:Lcom/airoha/utapp/sdk/TwsFota1562Fragment;
    invoke-static {v1}, Lcom/airoha/utapp/sdk/TwsFota1562Fragment;->pairBridgeReady(Lcom/airoha/utapp/sdk/TwsFota1562Fragment;)Z
    move-result v1
    if-nez v1, :pairbridge_commit
    return-void
    :pairbridge_commit
''' + call)
    p.write_text(s)
    p = decoded / (APP + 'TwsFota1562Fragment$RequestDfuThread$1.smali')
    s = p.read_text()
    marker = '    return-void\n.end method'
    if s.count(marker) != 2:  # constructor + run()
        raise ValueError('Unexpected DFU query callback shape')
    i = s.rindex(marker)
    p.write_text(s[:i] + '''    iget-object v0, p0, Lcom/airoha/utapp/sdk/TwsFota1562Fragment$RequestDfuThread$1;->this$1:Lcom/airoha/utapp/sdk/TwsFota1562Fragment$RequestDfuThread;
    iget-object v0, v0, Lcom/airoha/utapp/sdk/TwsFota1562Fragment$RequestDfuThread;->this$0:Lcom/airoha/utapp/sdk/TwsFota1562Fragment;
    invoke-static {v0}, Lcom/airoha/utapp/sdk/TwsFota1562Fragment;->pairBridgeRefresh(Lcom/airoha/utapp/sdk/TwsFota1562Fragment;)V

''' + s[i:])
    # The upstream diagnostics/export UI has literal provider authorities.
    # Keep the new app's private file sharing scoped to its own provider.
    for path in (decoded / APP).rglob('*.smali'):
        s = path.read_text()
        changed = s.replace('"' + cfg['source_package'] + '.provider"', '"' + cfg['output_package'] + '.provider"')
        if changed != s:
            path.write_text(changed)
    if sdk_fingerprint(decoded) != original_sdk:
        raise ValueError('SDK manager or response parser changed')
    after = ET.fromstring(manifest_path.read_text())
    if original_permissions != {p.get(ANDROID + 'name') for p in after.findall('uses-permission')}:
        raise ValueError('Application permissions changed')
    return original_sdk, original_permissions


def sign_apk(unsigned, target, signing_dir):
    signing_dir.mkdir(parents=True, exist_ok=True)
    key = signing_dir / 'pairbridge.p12'
    password_path = signing_dir / 'pairbridge.password'
    if key.exists() != password_path.exists():
        raise ValueError('Incomplete local signing identity; do not overwrite it')
    if not key.exists():
        password_path.write_text(secrets.token_urlsafe(32))
        password_path.chmod(0o600)
        env = os.environ.copy()
        env['PAIRBRIDGE_SIGN_PASS'] = password_path.read_text()
        run([tool('keytool'), '-genkeypair', '-alias', 'pairbridge', '-keystore', key, '-storetype', 'PKCS12',
             '-storepass:env', 'PAIRBRIDGE_SIGN_PASS', '-keyalg', 'RSA', '-keysize', '3072',
             '-sigalg', 'SHA256withRSA', '-validity', '3650', '-dname', 'CN=PairBridge Local Build'], env)
        key.chmod(0o600)
    env = os.environ.copy()
    env['PAIRBRIDGE_SIGN_PASS'] = password_path.read_text()
    run([tool('jarsigner'), '-keystore', key, '-storepass:env', 'PAIRBRIDGE_SIGN_PASS', '-sigalg', 'SHA256withRSA',
         '-digestalg', 'SHA-256', '-signedjar', target, unsigned, 'pairbridge'], env)
    result = run([tool('jarsigner'), '-verify', target])
    if 'jar verified' not in result:
        raise ValueError('Local APK signature verification failed')


def prepare(source, destination):
    cfg = PROFILE['app']
    checked_bytes(source, cfg)
    apktool = tool('apktool')
    if run([apktool, '--version']).strip() != cfg['apktool_version']:
        raise ValueError('Apktool version differs from the reviewed profile; see docs/BUILD.md')
    for name in ['java', 'keytool', 'jarsigner']:
        tool(name)
    destination = Path(destination)
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='android-', dir=local) as tmp:
        tmp = Path(tmp)
        decoded = tmp / 'decoded'
        run([apktool, 'd', source, '-o', decoded, '-p', local / 'framework'])
        original_sdk, original_permissions = patch_decoded(decoded)
        unsigned = tmp / 'unsigned.apk'
        run([apktool, 'b', decoded, '-o', unsigned, '-p', local / 'framework'])
        target = tmp / 'PairBridge.apk'
        sign_apk(unsigned, target, local / 'signing')
        verified = tmp / 'verified'
        run([apktool, 'd', target, '-o', verified, '-p', local / 'framework'])
        if sdk_fingerprint(verified) != original_sdk:
            raise ValueError('Rebuilt APK SDK instructions changed')
        manifest = ET.parse(verified / 'AndroidManifest.xml').getroot()
        app = manifest.find('application')
        if manifest.get('package') != cfg['output_package'] or app.get(ANDROID+'debuggable') != 'false':
            raise ValueError('Rebuilt app package/debug configuration differs')
        if original_permissions != {p.get(ANDROID+'name') for p in manifest.findall('uses-permission')}:
            raise ValueError('Rebuilt APK permissions differ')
        guard = (verified / 'smali/com/airoha/libfota1562/PairBridgeGuard.smali').read_text()
        for value in ['mAgentFotaState:I', 'mPartnerFotaState:I', '0x311', cfg['runtime_version'], cfg['runtime_flash']]:
            if value not in guard:
                raise ValueError('Reassembled commit guard does not match profile')
        with (destination / 'PairBridge.apk').open('xb') as output:
            output.write(target.read_bytes())
    report = {'source_sha256': cfg['source_sha256'], 'output_sha256': hashlib.sha256((destination/'PairBridge.apk').read_bytes()).hexdigest(),
              'package': cfg['output_package'], 'label': cfg['label'], 'debuggable': False,
              'internet_permission': False, 'permissions_match_original': True,
              'sdk_fota_classes_unchanged': len(original_sdk), 'commit_guard_states': cfg['runtime_states'],
              'signature':'Locally generated RSA/SHA-256, APK v1; reviewed target SDK retained',
              'private_key_published': False, 'new_wrapper_hardware_tested': False}
    write_json(destination / 'app-verification.json', report)
    return report

import os
import re
import subprocess
import sys
lines = subprocess.Popen('dir %s' % __file__, shell=True, stdout=subprocess.PIPE).stdout.readlines()
for line in lines:
    match = re.search('\[(.*)\]', line.decode('utf-8'))
    if match:
        script_dir = os.path.dirname(match.group(1)).replace('\\', '/')
        break
else:
    script_dir = sys.path[0]

sys.path.append(script_dir)
sys.path.append(script_dir + '/..')

from util.base import * # pylint: disable=unused-wildcard-import

class Mesa(Program):
    def __init__(self):
        parser = argparse.ArgumentParser(description='mesa')
        parser.epilog='''
examples:
python %(prog)s --sync --build
python %(prog)s --build --build-system autotools --rev-stride 50 --build-novulkan --rev 96700-96900
python %(prog)s --build --dir-install 20200810-126997-f7e7cf637e1 --build-replace
python %(prog)s --build --dir-install 20200810-126997-f7e7cf637e1 --build-replace --clean  # if build fails
python %(prog)s --hashtorev e58a10af640ba58b6001f5c5ad750b782547da76
python %(prog)s --revtohash 1
'''
        parser.add_argument('--repo', dest='repo', help='repo, can be freedesktop or chromeos', default='freedesktop')
        parser.add_argument('--init', dest='init', help='init', action='store_true')
        parser.add_argument('--sync', dest='sync', help='sync', action='store_true')
        parser.add_argument('--build', dest='build', help='build', action='store_true')
        parser.add_argument('--build-type', dest='build_type', help='build type', default='release')
        parser.add_argument('--build-target', dest='build_target', help='build target', default='all')
        parser.add_argument('--build-force', dest='build_force', help='no reset of source code', action='store_true')
        parser.add_argument('--build-novulkan', dest='build_novulkan', help='build novulkan', action='store_true')
        parser.add_argument('--upload', dest='upload', help='upload', action='store_true')
        parser.add_argument('--run', dest='run', help='run')
        parser.add_argument('--type', dest='type', help='type', default='i965')
        parser.add_argument('--branch', dest='branch', help='branch', default='master')
        parser.add_argument('--rev', dest='rev', help='rev, can be system, latest, or any specific revision', default='latest')
        parser.add_argument('--rev-stride', dest='rev_stride', help='rev stride', type=int, default=1)
        parser.add_argument('--clean', dest='clean', help='clean when build_force', action='store_true')
        parser.add_argument('--revtohash', dest='revtohash', help='get hash of commit rev starting from 1', type=int)
        parser.add_argument('--hashtorev', dest='hashtorev', help='get commit rev starting from 1 of hash')

        python_ver = Util.get_python_ver()
        if python_ver[0] == 3:
            super().__init__(parser)
        else:
            super(Mesa, self).__init__(parser)

        args = self.args
        self.build_type = args.build_type
        self.branch = args.branch
        build_force = args.build_force
        if args.branch != 'master':
            build_force = True
        self.build_force = build_force
        self.drm_dir = 'drm-master'
        self.mesa_dir = 'mesa-%s' % self.branch
        self.backup_dir = '%s/backup' % self.root_dir
        if args.build_target == 'all':
            self.targets = ['drm', 'mesa']
        else:
            self.targets = [args.build_target]
        self.hashes = []
        self.rev = args.rev

        self.run_cmd = args.run
        self.type = args.type

        self.args = args

        self._handle_ops()

    def init(self):
        if not os.path.exists(self.drm_dir):
            self._execute('git clone https://gitlab.freedesktop.org/mesa/drm %s' % self.drm_dir)

        if not os.path.exists(self.mesa_dir):
            if self.args.repo == 'chromeos':
                self._execute('git clone -b %s https://chromium.googlesource.com/chromiumos/third_party/mesa %s' % (self.branch, self.mesa_dir))
            else:
                self._execute('git clone -b %s https://gitlab.freedesktop.org/mesa/mesa %s' % (self.branch, self.mesa_dir))

    def sync(self):
        for dir in [self.drm_dir, self.mesa_dir]:
            Util.chdir('%s/%s' % (self.root_dir, dir))
            self._execute('git pull --rebase')

    def build(self):
        self._init_hash()

        if Util.HOST_OS == 'linux' and Util.HOST_OS_RELEASE == 'ubuntu':
            Util.ensure_pkg('meson libomxil-bellagio-dev libpciaccess-dev x11proto-dri3-dev x11proto-present-dev xutils-dev python-mako x11proto-gl-dev x11proto-dri2-dev libxcb-dri3-dev libxcb-present-dev libxshmfence-dev libx11-xcb-dev libxcb-glx0-dev libxcb-dri2-0-dev libxxf86vm-dev python3-mako')

        if re.search('-', str(self.rev)):
            tmp_revs = self.rev.split('-')
            min_rev = self._unify_to_rev(tmp_revs[0])
            max_rev = self._unify_to_rev(tmp_revs[1])
        elif self.rev == 'latest':
            min_rev = len(self.hashes)
            max_rev = min_rev
        else:
            tmp_rev = self._unify_to_rev(self.rev)
            min_rev = tmp_rev
            max_rev = tmp_rev

        Util.info('Begin to build rev from %s to %s' % (min_rev, max_rev))
        i = min_rev
        while i <= max_rev:
            if i > len(self.hashes):
                Util.info('Rev %s exceeds the max git revision' % i)
                break
            if i % self.args.rev_stride:
                i += 1
                continue
            self._build_one(i, self._rev_to_hash(i))
            i += 1

    def upload(self):
        rev_name, _ = Util.get_backup_dir(self.backup_dir, 'latest')
        rev_dir = '%s/%s' % (self.backup_dir, rev_name)
        rev_backup_file = '%s.tar.gz' % rev_dir
        if not os.path.exists(rev_backup_file):
            Util.chdir(self.backup_dir)
            Util.execute('tar zcf %s.tar.gz %s' % (rev_name, rev_name))

        if Util.check_server_backup(Util.BACKUP_SERVER, 'mesa', os.path.basename(rev_backup_file)):
            Util.info('Server already has rev %s' % rev_backup_file)
        else:
            Util.execute('scp %s wp@%s:/workspace/backup/%s/mesa/' % (rev_backup_file, Util.BACKUP_SERVER, Util.HOST_OS))

    def revtohash(self):
        tmp_rev = self.args.revtohash
        Util.info('The hash for rev %s is %s' % (tmp_rev, self._rev_to_hash(tmp_rev)))

    def hashtorev(self):
        tmp_hash = self.args.hashtorev
        Util.info('The rev of hash %s is %s' % (tmp_hash, _hash_to_rev(tmp_hash)))

    def run(self):
        Util.set_mesa('%s/backup' % self.root_dir, self.rev, self.type)
        self._execute(self.run_cmd)

    def _init_hash(self):
        if not self.hashes:
            Util.chdir('%s/%s' % (self.root_dir, self.mesa_dir))
            self.hashes = Util.get_repo_hashes()

    def _rev_to_hash(self, rev):
        self._init_hash()
        return self.hashes[rev - 1]

    def _hash_to_rev(self, hash):
        self._init_hash()
        for i, tmp_hash in reversed(list(enumerate(self.hashes))):
            if tmp_hash == hash:
                return i + 1
        Util.error('Could not find rev for hash %s' % hash)

    def _build_one(self, rev, hash):
        rev_dir = '%s/backup/%s' % (self.root_dir, Util.cal_backup_dir())

        if (os.path.exists(rev_dir) or os.path.exists('%s' % rev_dir)) and os.path.exists(rev_dir + '/lib/dri/i965_dri.so') and not self.build_force:
            Util.info('Rev %s has been built, so just skip it' % rev)
            return

        Util.info('Begin to build revision %s, hash %s' % (rev, hash))

        if self.args.clean or not self.build_force:
            self._clean(self.targets)
        elif self.branch != 'master':
            self._clean(['drm'])

        if 'drm' in self.targets:
            Util.chdir('%s/%s' % (self.root_dir, self.drm_dir))
            Util.ensure_nodir('build')
            Util.ensure_dir('build')
            build_cmd = 'meson build/ -Dprefix=%s -Dlibkms=true -Dintel=true -Dvmwgfx=false -Dradeon=false -Damdgpu=false -Dnouveau=false' % rev_dir
            if self.build_type == 'release':
                build_cmd += ' -Dbuildtype=release'
            elif self.build_type == 'debug':
                build_cmd += ' -Dbuildtype=debug'
            build_cmd += ' && ninja -j%s -C build/ install' % Util.CPU_COUNT

            result = self._execute(build_cmd)
            if result[0]:
                Util.ensure_nodir(rev_dir)
                return False

        if 'mesa' in self.targets:
            Util.chdir('%s/%s' % (self.root_dir, self.mesa_dir))
            Util.ensure_nodir('build')
            Util.ensure_dir('build')

            if not self.build_force:
                self._execute('git reset --hard %s' % hash)

            # update git hash
            result = Util.get_repo_hash()
            self._execute('echo "#define MESA_GIT_SHA1 \\\"git-%s\\\"" >src/mesa/main/git_sha1.h' % result[1].split()[0])
            build_cmd = 'PKG_CONFIG_PATH=%s/lib/x86_64-linux-gnu/pkgconfig meson build/ -Dprefix=%s -Dvulkan-drivers=intel -Ddri-drivers=i915,i965 -Ddri-drivers-path=%s/lib/dri -Dgles1=true -Dgles2=true -Dshared-glapi=true -Dplatforms=x11 -Dgbm=true -Ddri3=true -Dgallium-drivers=iris' % (rev_dir, rev_dir, rev_dir)
            relative_backup_dir = rev_dir
            if not self.args.build_novulkan:
                build_cmd += ' -Dvulkan-drivers=intel'
            if self.build_type == 'release':
                build_cmd += ' -Dbuildtype=release'
            elif self.build_type == 'debug':
                build_cmd += ' -Dbuildtype=debug'
            build_cmd += ' && ninja -j%s -C build/ install' % Util.CPU_COUNT

            result = self._execute(build_cmd)
            if result[0]:
                Util.ensure_nodir(rev_dir)
                return False

            for line in fileinput.input('%s/share/vulkan/icd.d/intel_icd.x86_64.json' % rev_dir, inplace=1):
                match = re.search('"library_path": "(.*)"', line)
                if match:
                    line = line.replace(match.group(1), '../../../lib/x86_64-linux-gnu/libvulkan_intel.so')
                sys.stdout.write(line)
            fileinput.close()

        return True

    def _clean(self, targets):
        if 'drm' in targets:
            Util.chdir('%s/%s' % (self.root_dir, self.drm_dir))
            self._execute('make distclean', exit_on_error=False)

        if 'mesa' in targets:
            Util.chdir('%s/%s' % (self.root_dir, self.mesa_dir))
            self._execute('make distclean', exit_on_error=False)

    def _unify_to_rev(self, str):
        if len(str) == 40:
            return _hash_to_rev(str)

        try:
            rev = int(str)
        except:
            Util.error('Input %s is not correct' % str)
        return rev

    def _handle_ops(self):
        args = self.args
        if args.init:
            self.init()
        if args.sync:
            self.sync()
        if args.build:
            self.build()
        if args.upload:
            self.upload()
        if args.revtohash:
            self.revtohash()
        if args.hashtorev:
            self.hashtorev()
        if args.run:
            self.run()

if __name__ == '__main__':
    Mesa()


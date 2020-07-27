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

class Dawn():
    def __init__(self):
        self._parse_arg()
        args = self.program.args

        if args.is_debug:
            build_type = 'debug'
        else:
            build_type = 'release'
        self.build_type_cap = build_type.capitalize()
        self.build_type = build_type
        self.symbol_level = args.symbol_level
        self.out_dir = Util.get_relative_out_dir(self.program.target_arch, self.program.target_os, self.symbol_level, no_component_build=True, dcheck=False)
        self.out_dir = '%s/%s' % (self.out_dir, self.build_type_cap)

        self.args = self.program.args
        self._handle_ops()

    def sync(self):
        self.program.execute('git pull')
        self.program.execute_gclient(cmd_type='sync')

    def runhooks(self):
        self.program.execute_gclient(cmd_type='runhooks')

    def makefile(self):
        gn_args = ''
        gn_args += ' symbol_level=%s' % self.symbol_level
        if self.symbol_level == 0:
            gn_args += ' blink_symbol_level=0'

        gn_args = ''
        if self.build_type == 'release':
            gn_args += ' is_debug=false'
        else:
            gn_args += ' is_debug=true'

        if self.args.no_component_build:
            gn_args += ' is_component_build=false'
        else:
            gn_args += ' is_component_build=true'

        gn_args += ' is_clang = true'
        quotation = Util.get_quotation()
        cmd = 'gn --args=%s%s%s gen %s' % (quotation, gn_args, quotation, self.out_dir)
        Util.info('GN ARGS: {}'.format(gn_args))
        result = self.program.execute(cmd)
        if result[0]:
            Util.error('Failed to makefile')

    def build(self):
        if self.args.build_target == 'default':
            tmp_targets = ['']
        else:
            tmp_targets = build_target.split(',')

        cmd = 'ninja -j' + str(Util.CPU_COUNT) + ' -C ' + self.out_dir
        cmd += ' %s' % ' '.join(tmp_targets)
        self.program.execute(cmd, show_duration=True)

    def test(self):
        if host_os == 'linux':
            mesa_rev_number = args.test_mesa_rev
            if mesa_rev_number == 'system':
                ensure_pkg('mesa-vulkan-drivers')
                info('Use system Mesa')
            else:
                if mesa_rev_number == 'latest':
                    mesa_dir = self._get_latest('mesa')
                    mesa_rev_number = re.match('mesa-master-release-(.*)-', mesa_dir).group(1)
                else:
                    files = os.listdir(mesa_install_dir)
                    for file in files:
                        match = re.match('mesa-master-release-%s' % mesa_rev_number, file)
                        if match:
                            mesa_dir = file
                            break
                    else:
                        _error('Could not find mesa build %s' % mesa_rev_number)

                mesa_dir = mesa_install_dir + '/' + mesa_dir
                setenv('VK_ICD_FILENAMES', '%s/share/vulkan/icd.d/intel_icd.x86_64.json' % mesa_dir)
                info('Use mesa at %s' % mesa_dir)

        self.program.execute('%s/dawn_end2end_tests' % self.out_dir)

    def _get_latest(self, type):
        if type == 'mesa':
            rev_dir = mesa_install_dir
            rev_pattern = 'mesa-master-release-(.*)-'
        elif type == 'chrome':
            rev_dir = build_dir
            rev_pattern = '(.*).zip'

        latest_rev = -1
        latest_file = ''
        files = os.listdir(rev_dir)
        for file in files:
            match = re.search(rev_pattern, file)
            if match:
                tmp_rev = int(match.group(1))
                if tmp_rev > latest_rev:
                    latest_file = file
                    latest_rev = tmp_rev

        return latest_file

    def _parse_arg(self):
        global args, args_dict
        parser = argparse.ArgumentParser(description='Script about dawn',
                                        formatter_class=argparse.RawTextHelpFormatter,
                                        epilog='''
examples:
python %(prog)s --sync --makefile --build
''')

        parser.add_argument('--is-debug', dest='is_debug', help='is debug', action='store_true')
        parser.add_argument('--no-component-build', dest='no_component_build', help='no component build', action='store_true')
        parser.add_argument('--sync', dest='sync', help='sync', action='store_true')
        parser.add_argument('--runhooks', dest='runhooks', help='runhooks', action='store_true')
        parser.add_argument('--makefile', dest='makefile', help='generate makefile', action='store_true')
        parser.add_argument('--build', dest='build', help='build', action='store_true')
        parser.add_argument('--build-target', dest='build_target', help='build target', default='default')
        parser.add_argument('--symbol-level', dest='symbol_level', help='symbol level', type=int, default=0)
        parser.add_argument('--backup', dest='backup', help='backup', action='store_true')
        parser.add_argument('--backup-target', dest='backup_target', help='backup target')
        parser.add_argument('--test', dest='test', help='test', action='store_true')
        parser.add_argument('--test-mesa-rev', dest='test_mesa_rev', help='mesa revision', default='latest')

        self.program = Program(parser)

    def _handle_ops(self):
        args = self.program.args
        if args.sync:
            self.sync()
        if args.runhooks:
            self.runhooks()
        if args.makefile:
            self.makefile()
        if args.build:
            self.build()
        if args.backup:
            self.backup()
        if args.test:
            self.test()

if __name__ == '__main__':
    Dawn()

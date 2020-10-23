import os
import platform
import re
import subprocess
import sys

HOST_OS = platform.system().lower()
if HOST_OS == 'windows':
    lines = subprocess.Popen('dir %s' % __file__.replace('/', '\\'), shell=True, stdout=subprocess.PIPE).stdout.readlines()
    for line in lines:
        match = re.search(r'\[(.*)\]', line.decode('utf-8'))
        if match:
            script_dir = os.path.dirname(match.group(1)).replace('\\', '/')
            break
    else:
        script_dir = sys.path[0]
else:
    lines = subprocess.Popen('ls -l %s' % __file__, shell=True, stdout=subprocess.PIPE).stdout.readlines()
    for line in lines:
        match = re.search(r'.* -> (.*)', line.decode('utf-8'))
        if match:
            script_dir = os.path.dirname(match.group(1))
            break
    else:
        script_dir = sys.path[0]

sys.path.append(script_dir)
sys.path.append(script_dir + '/..')

from util.base import * # pylint: disable=unused-wildcard-import

class Webgl(Program):
    SKIP_CASES = {
        #Util.LINUX: ['WebglConformance_conformance2_textures_misc_tex_3d_size_limit'],
        Util.LINUX: [],
        Util.WINDOWS: [],
        Util.DARWIN: [],
    }

    def __init__(self):
        parser = argparse.ArgumentParser(description='Chrome Drop WebGL')

        parser.add_argument('--build', dest='build', help='build', action='store_true')
        parser.add_argument('--build-chrome-rev', dest='build_chrome_rev', help='Chrome rev to build', default='latest')
        parser.add_argument('--build-chrome-dcheck', dest='build_chrome_dcheck', help='Build Chrome with dcheck', action='store_true')
        parser.add_argument('--build-skip-sync', dest='build_skip_sync', help='skip sync during build', action='store_true')
        parser.add_argument('--build-skip-build-chrome', dest='build_skip_build_chrome', help='skip building chrome during build', action='store_true')
        parser.add_argument('--build-skip-backup-chrome', dest='build_skip_backup_chrome', help='skip backing up chrome during build', action='store_true')
        parser.add_argument('--build-skip-mesa', dest='build_skip_mesa', help='skip skip building mesa during build', action='store_true')
        parser.add_argument('--test', dest='test', help='test', action='store_true')
        parser.add_argument('--test-chrome-rev', dest='test_chrome_rev', help='Chromium revision', default='latest')
        parser.add_argument('--test-mesa-rev', dest='test_mesa_rev', help='mesa revision', default='latest')
        parser.add_argument('--test-filter', dest='test_filter', help='WebGL CTS suite to test against', default='all')  # For smoke test, we may use conformance/attribs
        parser.add_argument('--test-verbose', dest='test_verbose', help='verbose mode of test', action='store_true')
        parser.add_argument('--test-chrome', dest='test_chrome', help='test chrome', default='default')
        parser.add_argument('--test-target', dest='test_target', help='test target, split by comma, like "0,2"', default='all')
        parser.add_argument('--test-no-angle', dest='test_no_angle', help='test without angle', action='store_true')
        parser.add_argument('--batch', dest='batch', help='batch', action='store_true')
        parser.add_argument('--run', dest='run', help='run', action='store_true')
        parser.add_argument('--dryrun', dest='dryrun', help='dryrun', action='store_true')
        parser.add_argument('--email', dest='email', help='send test result via email', action='store_true')
        parser.add_argument('--mesa-type', dest='mesa_type', help='mesa type', default='default')
        parser.add_argument('--mesa-dir', dest='mesa_dir', help='mesa dir')

        parser.epilog = '''
python %(prog)s --batch
'''
        python_ver = Util.get_python_ver()
        if python_ver[0] == 3:
            super().__init__(parser)
        else:
            super(Webgl, self).__init__(parser)

        args = self.args

        root_dir = self.root_dir
        self.chrome_dir = '%s/chromium' % root_dir
        self.chrome_src_dir = '%s/src' % self.chrome_dir
        self.chrome_backup_dir = '%s/backup' % self.chrome_src_dir
        if args.mesa_dir:
            self.mesa_dir = args.mesa_dir
        else:
            self.mesa_dir = '%s/mesa' % root_dir
        self.mesa_build_dir = '%s/build' % self.mesa_dir
        self.mesa_backup_dir = '%s/backup' % self.mesa_dir
        self.test_dir = '%s/test' % root_dir
        test_chrome = args.test_chrome
        if Util.HOST_OS == Util.DARWIN:
            if test_chrome == 'default':
                test_chrome = 'canary'
        else:
            if test_chrome == 'default':
                test_chrome = 'build'
        self.test_chrome = test_chrome
        self.result_dir = '%s/result' % self.test_dir

        if Util.HOST_OS == Util.LINUX:
            mesa_type = args.mesa_type
            if mesa_type == 'default':
                if args.batch:
                    mesa_type = 'i965,iris'
                else:
                    mesa_type = 'i965'
            self.mesa_types = mesa_type.split(',')

        self.proxy = args.proxy
        self.build_skip_sync = args.build_skip_sync
        self.build_skip_build_chrome = args.build_skip_build_chrome
        self.build_skip_backup_chrome = args.build_skip_backup_chrome
        self.build_skip_mesa = args.build_skip_mesa
        self.build_chrome_rev = args.build_chrome_rev
        self.build_chrome_dcheck = args.build_chrome_dcheck
        self.test_mesa_rev = args.test_mesa_rev
        self.test_filter = args.test_filter
        self.test_verbose = args.test_verbose
        self.test_chrome_rev = args.test_chrome_rev
        self.test_target = args.test_target
        self.email = args.email
        self.test_no_angle = args.test_no_angle

        self.target_os = args.target_os
        if not self.target_os:
            self.target_os = Util.HOST_OS

        self._handle_ops()

    def build(self):
        # build mesa
        if Util.HOST_OS == Util.LINUX and not self.build_skip_mesa and not self.target_os == Util.CHROMEOS:
            Util.chdir(self.mesa_dir)
            if not self.build_skip_sync:
                self._execute('python %s/mesa/mesa.py --sync --root-dir %s' % (ScriptRepo.ROOT_DIR, self.mesa_dir))
            self._execute('python %s/mesa/mesa.py --build --root-dir %s' % (ScriptRepo.ROOT_DIR, self.mesa_dir))

        # build chrome
        if self.test_chrome == 'build':
            if not self.build_skip_sync:
                cmd = 'python %s --sync --runhooks --root-dir %s' % (Util.GNP_SCRIPT_PATH, self.chrome_dir)
                if self.build_chrome_rev != 'latest':
                    cmd += ' --rev %s' % self.build_chrome_rev
                self._execute(cmd, exit_on_error=False)
            if not self.build_skip_build_chrome and not self.target_os == Util.CHROMEOS:
                cmd = 'python %s --no-component-build --makefile --symbol-level 0 --build --build-target webgl --out-dir out --root-dir %s' % (Util.GNP_SCRIPT_PATH, self.chrome_dir)
                if self.build_chrome_dcheck:
                    cmd += ' --dcheck'
                self._execute(cmd)
            if not self.build_skip_backup_chrome:
                cmd = 'python %s --backup --backup-target webgl --out-dir out --root-dir %s' % (Util.GNP_SCRIPT_PATH, self.chrome_dir)
                if self.target_os == Util.CHROMEOS:
                    cmd += ' --target-os chromeos'
                self._execute(cmd)

    def test(self, mesa_type=''):
        if self.target_os == Util.CHROMEOS:
            return
        Util.clear_proxy()

        if Util.HOST_OS == Util.LINUX:
            self.test_mesa_rev = Util.set_mesa(self.mesa_backup_dir, self.test_mesa_rev, mesa_type)

        common_cmd = 'vpython content/test/gpu/run_gpu_integration_test.py webgl_conformance --disable-log-uploads'
        if self.test_chrome == 'build':
            self.chrome_rev = self.test_chrome_rev
            (chrome_rev_dir, self.chrome_rev) = Util.get_backup_dir(self.chrome_backup_dir, self.chrome_rev)
            chrome_rev_dir = '%s/%s' % (self.chrome_backup_dir, chrome_rev_dir)
            Util.chdir(chrome_rev_dir, verbose=True)
            Util.info('Use Chrome at %s' % chrome_rev_dir)

            if Util.HOST_OS == Util.WINDOWS:
                chrome = 'out\Release\chrome.exe'
            else:
                if os.path.exists('out/Release/chrome'):
                    chrome = 'out/Release/chrome'
                else:
                    chrome = 'out/Default/chrome'

            common_cmd += ' --browser=exact --browser-executable=%s' % chrome
        else:
            common_cmd += ' --browser=%s' % self.test_chrome
            Util.chdir(self.chrome_src_dir)
            self.chrome_rev = self.test_chrome
            if Util.HOST_OS == Util.DARWIN:
                if self.test_chrome == 'canary':
                    chrome = '"/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"'
                else:
                    Util.error('test_chrome is not supported')
            elif Util.HOST_OS == Util.LINUX:
                if self.test_chrome == 'canary':
                    chrome = '/usr/bin/google-chrome-unstable'
                elif self.test_chrome == 'stable':
                    chrome = '/usr/bin/google-chrome-stable'
                else:
                    Util.error('test_chrome is not supported')
            else:
                Util.error('test_chrome is not supported')

        if self.args.run:
            param = '--enable-experimental-web-platform-features --disable-gpu-process-for-dx12-vulkan-info-collection --disable-domain-blocking-for-3d-apis --disable-gpu-process-crash-limit --disable-blink-features=WebXR --js-flags=--expose-gc --disable-gpu-watchdog --autoplay-policy=no-user-gesture-required --disable-features=UseSurfaceLayerForVideo --enable-net-benchmarking --metrics-recording-only --no-default-browser-check --no-first-run --ignore-background-tasks --enable-gpu-benchmarking --deny-permission-prompts --autoplay-policy=no-user-gesture-required --disable-background-networking --disable-component-extensions-with-background-pages --disable-default-apps --disable-search-geolocation-disclosure --enable-crash-reporter-for-testing --disable-component-update'
            param += ' --use-gl=angle'
            if Util.HOST_OS == Util.LINUX and self.test_no_angle:
                param += ' --use-gl=desktop'
            self._execute('%s %s http://wp-27.sh.intel.com/workspace/project/WebGL/sdk/tests/webgl-conformance-tests.html?version=2.0.1' % (chrome, param))
            return

        if self.test_filter != 'all':
            common_cmd += ' --test-filter=*%s*' % self.test_filter
        skip_filter = self.SKIP_CASES[Util.HOST_OS]
        if skip_filter:
            for skip_tmp in skip_filter:
                common_cmd += ' --skip=%s' % skip_tmp
        if self.test_verbose:
            common_cmd += ' --verbose'

        Util.ensure_dir(self.result_dir)
        datetime = Util.get_datetime()

        COMB_INDEX_WEBGL = 0
        COMB_INDEX_BACKEND = 1
        if Util.HOST_OS in [Util.LINUX, Util.DARWIN]:
            all_combs = [['2.0.1']]
        elif Util.HOST_OS == Util.WINDOWS:
            all_combs = [
                ['1.0.3', 'd3d9'],
                ['1.0.3', 'd3d11'],
                ['1.0.3', 'gl'],
                ['2.0.1', 'd3d11'],
                ['2.0.1', 'gl'],
            ]

        test_combs = []
        if self.test_target == 'all':
            test_combs = all_combs
        else:
            for i in self.test_target.split(','):
                test_combs.append(all_combs[int(i)])

        final_num_regressions = 0
        if self.build_chrome_dcheck:
            dcheck = 'true'
        else:
            dcheck = 'false'
        final_summary = 'Final summary (chrome_rev: %s, dcheck: %s):\n' % (self.chrome_rev, dcheck)
        final_details = 'Final details:\n'
        for comb in test_combs:
            extra_browser_args = '--disable-backgrounding-occluded-windows'
            if Util.HOST_OS == Util.LINUX and self.test_no_angle:
                extra_browser_args += ',--use-gl=desktop'
            cmd = common_cmd + ' --webgl-conformance-version=%s' % comb[COMB_INDEX_WEBGL]
            result_file = ''
            if Util.HOST_OS == Util.LINUX:
                result_file = '%s/%s-%s-%s-%s-%s.log' % (self.result_dir, datetime, self.chrome_rev, mesa_type, self.test_mesa_rev, comb[COMB_INDEX_WEBGL])
            elif Util.HOST_OS == Util.WINDOWS:
                extra_browser_args += ' --use-angle=%s' % comb[COMB_INDEX_BACKEND]
                result_file = '%s/%s-%s-%s-%s.log' % (self.result_dir, datetime, self.chrome_rev, comb[COMB_INDEX_WEBGL], comb[COMB_INDEX_BACKEND])
            elif Util.HOST_OS == Util.DARWIN:
                result_file = '%s/%s-%s-%s.log' % (self.result_dir, datetime, self.chrome_rev, comb[COMB_INDEX_WEBGL])

            if extra_browser_args:
                cmd += ' --extra-browser-args="%s"' % extra_browser_args
            cmd += ' --write-full-results-to %s' % result_file
            test_timer = Timer()
            result = self._execute(cmd, exit_on_error=False, show_duration=True)
            num_regressions, result = Util.get_gpu_integration_result(result_file)
            final_num_regressions += num_regressions
            final_summary += result.split('\n')[0] + '\n'
            final_details += result
            Util.info(result)

        Util.info(final_details)
        Util.info(final_summary)

        log_file = self.log_file
        Util.write_file(log_file, [final_details], mode='a+')
        Util.write_file(log_file, [final_summary], mode='a+')


        if Util.HOST_OS == Util.LINUX:
            subject = 'WebGL CTS on Chrome %s and Mesa %s %s has %s Regression' % (self.chrome_rev, mesa_type, self.test_mesa_rev, num_regressions)
        else:
            subject = 'WebGL CTS on Chrome %s has %s Regression' % (self.chrome_rev, num_regressions)
        if self.args.batch and Util.HOST_OS == Util.LINUX or self.email:
            Util.send_email('webperf@intel.com', 'yang.gu@intel.com', subject, '%s\n%s' % (final_summary, final_details))

    def run(self):
        if Util.HOST_OS == Util.LINUX:
            if len(self.mesa_types) > 1:
                Util.error('Only one mesa_type is support for run')
            mesa_type = self.mesa_types[0]
            self.test(mesa_type=mesa_type)
        else:
            self.test()

    def batch(self):
        self.build()
        if Util.HOST_OS == Util.LINUX:
            for mesa_type in self.mesa_types:
                self.test(mesa_type=mesa_type)
        else:
            self.test()

    def _handle_ops(self):
        args = self.args
        if args.build:
            self.build()
        if args.test:
            if re.search(',', args.mesa_type) and Util.HOST_OS == Util.LINUX:
                Util.error('Only one mesa_type can be designated!')
            self.test(mesa_type=args.mesa_type)
        if args.run:
            self.run()
        if args.batch:
            self.batch()

if __name__ == '__main__':
    Webgl()

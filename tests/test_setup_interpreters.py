"""Reproduce Anaconda discovery and setup/launcher interpreter mismatches."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import python_environment


class RuntimeProbeTests(unittest.TestCase):
    def test_supported_alternative_python_requires_online_wheels(self):
        with patch.object(sys,'version_info',(3,13,1)),patch.object(python_environment.struct,'calcsize',return_value=8), \
             patch.dict(sys.modules,{'tkinter':types.ModuleType('tkinter')}):
            info=python_environment.runtime_info()
        self.assertTrue(info['compatible'])
        self.assertFalse(info['offline_wheels'])

    def test_old_or_32bit_python_is_rejected(self):
        for version,bits in [((3,9,9),8),((3,12,3),4)]:
            with self.subTest(version=version,bits=bits),patch.object(sys,'version_info',version), \
                 patch.object(python_environment.struct,'calcsize',return_value=bits), \
                 patch.dict(sys.modules,{'tkinter':types.ModuleType('tkinter')}):
                self.assertFalse(python_environment.runtime_info()['compatible'])


@unittest.skipUnless(sys.platform=='win32','Windows interpreter discovery and launchers')
class WindowsSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='H2RES setup (test) ')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        for name in ['setup_windows.ps1','launch_data_preparation.ps1','preparation_python.ps1','python_environment.py']:
            shutil.copy2(ROOT/name,self.root/name)
        (self.root/'PACKAGE_MANIFEST.json').write_text('{}')
        self.environment=os.environ.copy()
        self.environment.pop('PYTHONPATH',None)
        self.environment['DATA_PREPARATION_PYTHON']=sys.executable

    def powershell(self,script):
        path=self.root/'test_case.ps1'
        path.write_text("$ErrorActionPreference='Stop'\n"+script,encoding='utf-8')
        return subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',str(path)],
                              cwd=self.root,env=self.environment,capture_output=True,text=True,timeout=30)

    def launcher(self):
        return subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
                               '-File',str(self.root/'launch_data_preparation.ps1'),'-Check'],
                              cwd=self.root,env=self.environment,capture_output=True,text=True,timeout=30)

    def fake_gui(self,fail=False):
        text="from pathlib import Path\nimport sys,json\nPath(__file__).with_suffix('.invoked').touch()\n"
        if fail:text+="sys.stderr.write('Missing preparation package: osmium\\n')\nsys.exit(2)\n"
        else:text+="print(json.dumps(dict(startup_check_passed=True,python=sys.executable)))\n"
        (self.root/'data_preparation_gui.py').write_text(text)

    def make_environment(self):
        subprocess.run([sys.executable,'-m','venv','--without-pip',str(self.root/'.venv')],check=True,capture_output=True)

    def test_release_without_setup_cannot_open_an_unprepared_global_python(self):
        self.fake_gui()
        result=self.launcher()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('SETUP_WINDOWS.bat',result.stdout)
        self.assertFalse((self.root/'data_preparation_gui.invoked').exists())

    def test_project_environment_wins_over_external_override(self):
        self.make_environment();self.fake_gui()
        result=self.launcher()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('.venv',result.stdout)

    def test_missing_dependencies_cannot_trigger_fallback_to_anaconda(self):
        self.make_environment();self.fake_gui(fail=True)
        result=self.launcher()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('osmium',result.stdout)
        self.assertIn('will not fall back',result.stdout)
        self.assertNotIn('Starting Energy',result.stdout)

    def test_anaconda_folder_is_discovered_without_being_on_path(self):
        profile=self.root/'user'
        interpreter=profile/'anaconda3/python.exe'
        interpreter.parent.mkdir(parents=True);interpreter.touch()
        self.environment['USERPROFILE']=str(profile)
        result=self.powershell(". (Join-Path $PSScriptRoot 'preparation_python.ps1')\nGet-PreparationPythonCandidates $PSScriptRoot | ConvertTo-Json -Compress")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(str(interpreter),json.loads(result.stdout))

    def test_explicit_anaconda_313_uses_online_plan_and_offline_is_rejected(self):
        interpreter=self.root/'anaconda3/python.exe'
        interpreter.parent.mkdir();interpreter.touch()
        base=""". (Join-Path $PSScriptRoot 'preparation_python.ps1')
function Get-PreparationPythonInfo { param($Executable,$Root)
 return [pscustomobject]@{executable=$Executable;compatible=$true;offline_wheels=$false;version_text='3.13.1';bits=64;tkinter_available=$true;tkinter_error=''} }
Select-PreparationSetupPython -Root $PSScriptRoot -PythonExe (Join-Path $PSScriptRoot 'anaconda3/python.exe')"""
        result=self.powershell(base+' | ConvertTo-Json -Compress')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(json.loads(result.stdout)['offline_wheels'])
        result=self.powershell(base+' -Offline')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Offline setup requires',result.stderr)


if __name__=='__main__':unittest.main()

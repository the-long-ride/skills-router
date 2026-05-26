#!/usr/bin/env node

const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const wrapperRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(wrapperRoot, '..');
const localSrcDir = path.join(repoRoot, 'src');
const hasLocalSource = fs.existsSync(path.join(localSrcDir, 'skills_router', 'cli.py'));

function readWrapperVersion() {
  const packageJsonPath = path.join(wrapperRoot, 'package.json');
  try {
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
    if (typeof packageJson.version === 'string' && packageJson.version.length > 0) {
      return packageJson.version;
    }
  } catch (e) {
    // Fall through to the shared error below.
  }

  console.error('Error: Could not read npm wrapper version from package.json.');
  process.exit(1);
}

function getInstalledSkillsRouterVersion(pythonCommand) {
  try {
    return execFileSync(
      pythonCommand,
      [
        '-c',
        'from importlib.metadata import version; print(version("skills-router"))',
      ],
      { encoding: 'utf8' }
    ).trim();
  } catch (e) {
    return null;
  }
}

// Determine which python command is available (handles Windows vs macOS/Linux)
const pythonCandidates = ['python3', 'python', 'py'];
let pythonCmd = null;
for (const candidate of pythonCandidates) {
  try {
    execFileSync(candidate, ['--version'], { stdio: 'ignore' });
    pythonCmd = candidate;
    break;
  } catch (e) {
    // Try next candidate
  }
}

if (!pythonCmd) {
  console.error('Error: Python is not installed or not in system PATH.');
  process.exit(1);
}

const childEnv = { ...process.env };
childEnv.PYTHONUTF8 = childEnv.PYTHONUTF8 || '1';
childEnv.PYTHONIOENCODING = childEnv.PYTHONIOENCODING || 'utf-8';
if (hasLocalSource) {
  childEnv.PYTHONPATH = childEnv.PYTHONPATH
    ? `${localSrcDir}${path.delimiter}${childEnv.PYTHONPATH}`
    : localSrcDir;
} else {
  // 1. Ensure the published npm wrapper runs the matching PyPI package version.
  const wrapperVersion = readWrapperVersion();
  const installedVersion = getInstalledSkillsRouterVersion(pythonCmd);
  if (installedVersion !== wrapperVersion) {
    const packageSpec = `skills-router==${wrapperVersion}`;
    console.log(`Installing ${packageSpec} via pip...`);
    try {
      execFileSync(pythonCmd, ['-m', 'pip', 'install', packageSpec], { stdio: 'inherit' });
    } catch (err) {
      console.error(`Error: Failed to install ${packageSpec} via pip.`);
      process.exit(1);
    }
  }
}

// 2. Forward arguments to the Python CLI
const args = process.argv.slice(2);
const pythonProcess = spawn(pythonCmd, ['-m', 'skills_router.cli', ...args], {
  stdio: 'inherit',
  env: childEnv
});

pythonProcess.on('close', (code) => {
  process.exit(code);
});

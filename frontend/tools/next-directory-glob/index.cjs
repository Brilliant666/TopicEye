// Only the directory-discovery API used by @next/eslint-plugin-next.
// Do not use this adapter as a general fast-glob replacement.
const { globSync: glob } = require('tinyglobby');
const { isAbsolute } = require('node:path');

exports.globSync = function globSync(pattern, options) {
  if (typeof pattern !== 'string' || options?.onlyDirectories !== true ||
      Object.keys(options).some(key => key !== 'onlyDirectories')) {
    throw new TypeError('Unsupported Next directory glob contract');
  }
  const normalized = pattern.replace(/\\/g, '/').replace(/(^|\/)\*\*\/?$/, '$1**/*');
  return glob(normalized, { onlyDirectories: true, expandDirectories: false, absolute: isAbsolute(normalized) })
    .map(path => path.replace(/\/$/, ''));
};

module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
  plugins: ['@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
  ],
  settings: { react: { version: '18.3' } },
  rules: {
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',
    // TS owns unused-var checking; let it handle leading-underscore ignore patterns.
    'no-unused-vars': 'off',
    '@typescript-eslint/no-unused-vars': [
      'warn',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
    ],
  },
  overrides: [
    {
      files: ['*.cjs'],
      env: { node: true, browser: false },
      parser: 'espree',
    },
    {
      // Sandbox lives behind import.meta.env.DEV and exists to mock arbitrary
      // backend payloads at runtime; the slider-fed records are intentionally any.
      files: ['src/features/sandbox/**/*.{ts,tsx}'],
      rules: { '@typescript-eslint/no-explicit-any': 'off' },
    },
  ],
}

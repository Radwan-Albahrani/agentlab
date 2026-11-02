import js from '@eslint/js';
import stylex from '@stylexjs/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'e2e', 'node_modules'] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  reactHooks.configs.flat['recommended-latest'],
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { '@stylexjs': stylex },
    rules: {
      '@stylexjs/valid-styles': 'error',
      '@stylexjs/no-unused': 'error',
      '@stylexjs/valid-shorthands': 'error',
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
      // In this API an empty string or 0 means "not set", so `||` falling back on them is intended.
      '@typescript-eslint/prefer-nullish-coalescing': ['error', { ignorePrimitives: { string: true, number: true } }],
      // Screens and app components use our wrappers in ui/, never Base UI directly.
      'no-restricted-imports': [
        'error',
        { patterns: [{ group: ['@base-ui/react', '@base-ui/react/*'], message: 'Use the wrapper in src/ui/.' }] },
      ],
    },
  },
  {
    files: ['src/ui/**/*.{ts,tsx}'],
    rules: { 'no-restricted-imports': 'off' },
  },
  {
    files: ['**/*.test.{ts,tsx}', '*.config.{js,ts}'],
    extends: [tseslint.configs.disableTypeChecked],
    rules: { '@typescript-eslint/no-non-null-assertion': 'off' }, // fixtures are known to be there
  },
);

export default {
  plugins: ["@double-great/stylelint-a11y"],
  overrides: [
    {
      files: ["**/*.html"],
      customSyntax: "postcss-html",
    },
  ],
  rules: {
    // Focus on catching actual CSS errors, not style conventions
    // Syntax errors are caught by the parser automatically

    // Catch potential mistakes
    "block-no-empty": true,
    "declaration-block-no-duplicate-properties": true,
    "font-family-no-missing-generic-family-keyword": true,
    "function-calc-no-unspaced-operator": true,
    "no-duplicate-at-import-rules": true,
    "no-invalid-double-slash-comments": true,
    "property-no-unknown": true,
    "selector-pseudo-class-no-unknown": true,
    "selector-pseudo-element-no-unknown": true,
    "unit-no-unknown": true,

    // Accessibility checks
    "a11y/media-prefers-reduced-motion": null, // Disabled - too strict for initial setup
    "a11y/no-outline-none": [true, {
      severity: "warning"  // Allow :focus:not(:focus-visible) progressive enhancement
    }],
    "a11y/selector-pseudo-class-focus": [true, {
      severity: "error"  // Critical: interactive elements with :hover should have :focus
    }],
  },
};

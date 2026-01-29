import html from "eslint-plugin-html";

export default [
  {
    ignores: ["eslint.config.js", "stylelint.config.js", "node_modules/**"],
  },
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
    },
    rules: {
      "no-undef": "off",
      "no-unused-vars": "off",
    },
  },
  {
    files: ["**/*.html"],
    plugins: { html },
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
    },
    rules: {
      "no-undef": "off",
      "no-unused-vars": "off",
    },
  },
];

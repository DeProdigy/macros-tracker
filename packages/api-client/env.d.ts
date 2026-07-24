/**
 * Ambient types for the build-time environment variables this package reads.
 *
 * Deliberately narrow: @types/node would declare a whole Node runtime that does
 * not exist in React Native. Expo statically replaces `process.env.EXPO_PUBLIC_*`
 * with literals when it bundles, so this is the only shape actually available.
 */
declare const process: {
  env: {
    /** Base URL of the Django API. Public — never put a secret behind this prefix. */
    EXPO_PUBLIC_API_URL?: string;
  };
};

# MAC-20 — EAS build config and first device build against deployed API

Approved 21 Aug 2026. Linear:
[MAC-20](https://linear.app/hintology/issue/MAC-20/eas-build-config-and-first-device-build-against-deployed-api).

## Context

Closes the walking skeleton: a real build, on a real phone, talking to the
deployed API. MAC-18 put Django on Railway; this points the app at it.

The ticket sat in Backlog because the Apple Developer membership lapsed in 2019.
It is renewed as of 21 Aug 2026, which is what unblocked this. MAC-30 has been
waiting on the same thing for its last two acceptance criteria.

## State found on `main`

Confirmed rather than assumed:

| Thing | Value |
| -- | -- |
| Railway API | `https://api-production-2884.up.railway.app` |
| `GET /api/health/` | 200, `{"status":"ok","database":true,...}` |
| Bundle identifier | `com.hintology.macrostracker`, already set (commit `3a50fdd`) |
| Icon and splash | placeholders already in `assets/`, already wired in `app.json` |
| `eas.json` | absent |
| `eas-cli` | not installed |
| Expo account | not logged in |

So the ticket is smaller than it reads. Three of its criteria were quietly
satisfied by earlier work.

## Split: what is code, and what needs a human

This is the first ticket where most of the work is not a diff. EAS build
credentials are interactive by design — Apple's sign-in, the two-factor prompt,
and the device registration profile all need a person and a phone.

**In this PR:**

- `apps/mobile/eas.json` with the three profiles
- `EXPO_PUBLIC_API_URL` per profile
- home screen moved from `usePing` to `useHealth`
- `.env.example` note on why the local value is not the build value

**Run by hand, in order:**

```bash
eas login                                        # Expo account, free tier
eas init                                         # links the project, writes extra.eas.projectId
eas device:create                                # registers the phone
eas build --profile development --platform ios   # prompts for Apple ID
```

`eas init` writes a project id back into the app config, so that edit lands as a
follow-up commit rather than being invented here. Guessing it would produce a
build that fails at credential resolution.

## Approach

### Build profiles

Three, matching doc 09's release pipeline.

| Profile | `developmentClient` | `distribution` | For |
| -- | -- | -- | -- |
| `development` | true | internal | The dev client on a registered device. This ticket |
| `preview` | false | internal | A shareable build with no dev tooling |
| `production` | false | store (default) | App Store, a later epic |

`development` sets `ios.simulator: false` explicitly. A simulator build needs no
paid membership and is the tempting shortcut, but it cannot run
`expo-apple-authentication` and would not satisfy MAC-30 either. Writing the
`false` down is cheaper than rediscovering that.

`production` sets `autoIncrement: true` with `cli.appVersionSource: "remote"`, so
EAS owns the build number. The alternative is a `buildNumber` in `app.json` that
every developer forgets to bump and that conflicts on merge.

### `EXPO_PUBLIC_API_URL` is set per profile, and that is the whole point

`EXPO_PUBLIC_*` values are inlined into the JS bundle at build time, not read at
runtime. A build without the var falls back to the `http://localhost:8000`
default in `packages/api-client/http-client.ts`. On a phone, localhost is the
phone, so every request fails with a connection error that names nothing.

All three profiles point at Railway. There is one deployed environment, so
inventing a staging URL for `preview` would be fiction.

The URL is not a secret. It is a public HTTPS endpoint that anyone with the app
can see in a proxy, which is exactly why nothing else may go in this block.

### Health, not ping

The ticket asks for `GET /api/health/` through a generated hook. The home screen
called `usePing`.

The two are different on purpose, and the API's own serializer docstring says so:
ping answers "is the process up?", health answers "can this process serve a
request?", because health runs a real query. On a device build pointed at
Railway, that difference is the entire walking skeleton — phone, API, Postgres.
Ping would go green with the database on fire.

The screen also renders the 503 body rather than the word "unreachable". Health
answers 503 with a full `Health` body naming the failed dependency, and
`customFetch` throws on any non-2xx, so that body arrives as `error` and never as
`data`. Collapsing it to "unreachable" would throw away the one useful case:
process up, database down. `unhealthyBody` pulls it back out.

## Alternatives rejected

**A simulator build to start.** No paid membership needed, and it would have let
this ticket start weeks ago. It cannot run the native Apple auth module, so it
unblocks nothing that matters and the ticket says so itself.

**`eas-cli` as a devDependency.** Tempting for version pinning. It is a 518
package install that every workspace member would pay for, and EAS expects a
global. The `cli.version` field in `eas.json` enforces a floor instead, which is
the mechanism built for this.

**Inventing the `extra.eas.projectId`.** `eas init` writes it. A hand-typed one
resolves to nothing and fails at credential lookup with an error about
permissions rather than about the id.

**A staging Railway environment for `preview`.** One deployed environment exists.
A second URL in the config that points at the same place is a lie waiting to
drift.

## Concepts in play

**Build-time inlining versus runtime config.** `EXPO_PUBLIC_*` is a find-and-
replace performed by the bundler. There is no environment to read on a phone, so
the value is frozen into the JavaScript. This is why the var is per-profile and
why a secret in it is unrecoverable: it ships inside the app, and shipping a new
app is the only way to change it. The runtime-config alternative is fetching
config from the server at boot, which trades a fixed value for an extra request
that can fail before the app has anything to show.

**Development build versus Expo Go.** Expo Go is a pre-built app containing a
fixed set of native modules. Anything outside that set — `expo-apple-
authentication` here, `expo-camera` in E4 — cannot be loaded into it, because
native code cannot be added at runtime. A development build is the same JS
tooling wrapped in a native app compiled with your modules. Right choice as soon
as one custom native module appears, which is now.

**`instanceof` across a jest module mock.** `index.test.tsx` defines a stand-in
`ApiError` inside the `jest.mock` factory, because the screen narrows on
`instanceof` and a plain object would never match. It uses plain class fields
rather than TypeScript parameter properties: babel rewrites those into
assignments that jest's out-of-scope guard reads as an external reference, and
the whole suite fails to compile with an error naming the parameter.

## Blast radius

Small and mostly additive. One new config file, one screen rewritten, its test
rewritten alongside. No API change, so nothing for `api-client-drift`.

The screen change is the only thing that could surprise: `usePing` now has no
callers. It stays in the generated client because it is generated, and
`/api/ping/` stays as an operational probe.

## Deliberately unhandled

- **`eas submit` and App Store Connect.** A later epic per doc 09. No `submit`
  block here, since an empty one is a placeholder pretending to be config
- **`expo-updates` and OTA channels.** Not installed. Profiles carry no `channel`
- **Android builds.** iOS-only for now
- **CI-triggered builds.** Builds are run by hand while there is one developer

## Open questions

**Auto-renew on the Apple membership.** It lapsed once already. A second lapse
after the app ships pulls it from the store. Worth turning on, and it is a
checkbox rather than a ticket.

**The icon and splash are still Expo's placeholders.** Fine for a development
build, and a rejection for a store build. Belongs in the App Store epic, not
here, but it should not be a surprise when it lands there.

import { Redirect, router } from "expo-router";
import { StyleSheet, View } from "react-native";

import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import { Label, Lead, Title } from "@/components/ui/text";
import { needsOnboarding } from "@/lib/onboarding";
import { useSession } from "@/lib/session";
import { colors, space } from "@/lib/theme";

/** The mandatory handoff from saved targets to the first logging slice. */
export default function FirstFoodPrompt() {
  const session = useSession();

  if (session.status === "loading") return null;
  if (session.status === "signedOut") return <Redirect href="/login" />;
  if (needsOnboarding(session.user)) return <Redirect href="/onboarding" />;

  return (
    <Screen contentStyle={styles.page}>
      <View style={styles.block}>
        <Label color={colors.accent}>TARGETS SAVED</Label>
        <Title style={styles.title}>Now log your first food.</Title>
        <Lead style={styles.body}>
          Your targets are ready. Your first entry will start filling the day.
        </Lead>
      </View>
      <Button
        onPress={() => router.push("/log-food")}
        style={styles.button}
        title="Log your first food"
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  block: { gap: space.md },
  body: { lineHeight: 28 },
  button: { marginTop: space.section },
  page: { justifyContent: "center", paddingHorizontal: space.xl },
  title: { marginTop: space.xs },
});

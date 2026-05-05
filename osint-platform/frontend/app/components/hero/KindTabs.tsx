"use client";
import { motion } from "framer-motion";
import { AtSign, Phone, User, Hash } from "lucide-react";
import type { QueryKind } from "../../lib/types";

const TABS: Array<{ id: QueryKind; label: string; icon: React.ComponentType<{ className?: string }>; ph: string }> = [
  { id: "name",     label: "Name",     icon: User,   ph: "e.g. Jane Doe" },
  { id: "email",    label: "Email",    icon: AtSign, ph: "e.g. jane.doe@example.com" },
  { id: "phone",    label: "Phone",    icon: Phone,  ph: "e.g. +1 415 555 1212" },
  { id: "username", label: "Username", icon: Hash,   ph: "e.g. janedoe" },
];

export function KindTabs({
  value, onChange,
}: {
  value: QueryKind;
  onChange: (k: QueryKind, placeholder: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {TABS.map((t, i) => {
        const Icon = t.icon;
        const active = value === t.id;
        return (
          <motion.button
            key={t.id}
            type="button"
            data-active={active}
            onClick={() => onChange(t.id, t.ph)}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: 0.04 * i }}
            whileHover={{ y: -1 }}
            className="kind-tab"
          >
            <Icon className="w-3.5 h-3.5" />
            {t.label}
          </motion.button>
        );
      })}
    </div>
  );
}

export const KIND_PLACEHOLDER: Record<QueryKind, string> = {
  name: "e.g. Jane Doe",
  email: "e.g. jane.doe@example.com",
  phone: "e.g. +1 415 555 1212",
  username: "e.g. janedoe",
};

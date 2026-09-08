import { PlusIcon, ChevronDownIcon } from "../components/icons";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, Department, User } from "../api/client";
import { usePreferences } from "../settings/preferences";
import { useToast } from "../toast/ToastProvider";
import ConfirmDialog from "../toast/ConfirmDialog";

const inputClass =
  "border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 w-full";
const panelClass = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";
const buttonPrimary =
  "rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50";
const buttonSecondary =
  "rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800";
const buttonDanger =
  "rounded-lg border border-red-200 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/60 dark:text-red-300 dark:hover:bg-red-950/40";

/** Whether the backend's safety rules would refuse this change: you cannot
 *  demote, deactivate or delete yourself, nor the last active
 *  administrator. The server enforces it; disabling the control here just
 *  saves the round trip and explains itself in the tooltip. */
function guarded(target: User, self: User | null, users: User[]): string | null {
  const isSelf = self != null && target.id === self.id;
  const activeAdmins = users.filter((u) => u.role === "admin" && u.active !== false).length;
  const lastAdmin = target.role === "admin" && target.active !== false && activeAdmins <= 1;
  if (isSelf) return "self";
  if (lastAdmin) return "lastAdmin";
  return null;
}

export default function UsersPage({ user: self }: { user: User | null }) {
  const { t } = useTranslation();
  const [users, setUsers] = useState<User[]>([]);
  const { publicSettings } = usePreferences();
  const canInvite = !!publicSettings?.mail_enabled;
  // Departments exist only beside the shipment history: they decide who
  // sees whose kept shipments, and mean nothing without them.
  const historyOn = !!publicSettings?.history_enabled;
  const [departments, setDepartments] = useState<Department[]>([]);
  const loadDepartments = () =>
    api.departments().then(setDepartments).catch(() => setDepartments([]));
  useEffect(() => {
    if (historyOn) void loadDepartments();
  }, [historyOn]);
  const [form, setForm] = useState({ username: "", email: "", password: "", role: "user" });
  // With a mail server the invitation is the better default: the new
  // colleague picks their own password, so it never travels by chat or note.
  const [invite, setInvite] = useState(true);
  const [busy, setBusy] = useState(false);
  const [resetFor, setResetFor] = useState<number | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  // The one action that keeps a confirmation step: clearing two-factor is a
  // security action, so it gets a deliberate dialog rather than an undo.
  const [clearTwoFactorTarget, setClearTwoFactorTarget] = useState<User | null>(null);
  const toast = useToast();

  const load = () =>
    api
      .listUsers()
      .then(setUsers)
      .catch((e) => toast.error(String(e)));
  useEffect(() => {
    void load();
  }, []);

  const run = async (action: () => Promise<unknown>, done = "") => {
    setBusy(true);
    try {
      await action();
      await load();
      if (done) toast.success(done);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setBusy(false);
    }
  };

  const create = (e: React.FormEvent) => {
    e.preventDefault();
    const sendWelcome = canInvite && invite;
    void run(async () => {
      const created = await api.createUser({
        ...form,
        // An empty box means "no password typed": with an invitation the
        // colleague chooses one, without it the server refuses and says so.
        password: form.password.trim() ? form.password : undefined,
        send_welcome: sendWelcome,
      });
      setForm({ username: "", email: "", password: "", role: "user" });
      if (created.welcome_mail && created.welcome_mail !== "not_requested") {
        (created.welcome_mail === "sent" ? toast.success : toast.error)(
          created.welcome_mail === "sent"
            ? t("users.invited", { email: created.email })
            : created.welcome_mail === "no_mail_server"
              ? t("users.inviteNoMailServer")
              : t("users.inviteFailed", { reason: created.welcome_mail }),
        );
      }
    }, sendWelcome ? "" : t("users.created"));
  };

  const patch = (id: number, payload: Record<string, unknown>, done = "") =>
    run(() => api.updateUser(id, payload), done);

  const remove = (target: User) => {
    // Deferred delete: the row disappears now, the DELETE fires when the undo
    // window closes. Undo means the call never happened — which is why the
    // restored user keeps their password.
    setUsers((current) => current.filter((u) => u.id !== target.id));
    toast.undoable(t("toast.deletedUser", { name: target.username }), {
      execute: () => {
        api.deleteUser(target.id).then(load).catch((e) => {
          toast.error(String(e));
          void load();
        });
      },
      restore: () => setUsers((current) =>
        current.some((u) => u.id === target.id) ? current : [...current, target]),
    });
  };

  const guardText = (kind: string | null) =>
    kind === "self" ? t("users.guardSelf") : kind === "lastAdmin" ? t("users.guardLastAdmin") : undefined;

  return (
    <div className="collection-page page-enter space-y-6 max-w-4xl">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{t("users.title")}</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{t("users.intro")}</p>
      </div>

      <details className="surface collection-form">
        <summary><PlusIcon /><span>{t("users.newUser")}</span><ChevronDownIcon /></summary>
        <form onSubmit={create} className="collection-form-body space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="text-sm font-medium text-slate-800 dark:text-slate-200" htmlFor="new-username">
              {t("users.username")}
            </label>
            <input
              id="new-username"
              className={`${inputClass} mt-1`}
              value={form.username}
              minLength={3}
              required
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-800 dark:text-slate-200" htmlFor="new-email">
              {t("users.email")}
            </label>
            <input
              id="new-email"
              type="email"
              className={`${inputClass} mt-1`}
              value={form.email}
              required
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-800 dark:text-slate-200" htmlFor="new-password">
              {t("users.password")}
            </label>
            <input
              id="new-password"
              type="password"
              className={`${inputClass} mt-1`}
              value={form.password}
              minLength={8}
              required={!canInvite || !invite}
              disabled={canInvite && invite}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {canInvite && invite ? t("users.passwordByInvite") : t("users.passwordHint")}
            </p>
          </div>
          <div>
            <label className="text-sm font-medium text-slate-800 dark:text-slate-200" htmlFor="new-role">
              {t("users.role")}
            </label>
            <select
              id="new-role"
              className={`${inputClass} mt-1`}
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            >
              <option value="user">{t("users.roleUser")}</option>
              <option value="admin">{t("users.roleAdmin")}</option>
            </select>
          </div>
        </div>
        {canInvite && (
          <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={invite}
              onChange={(e) => setInvite(e.target.checked)}
            />
            <span>
              {t("users.invite")}
              <span className="block text-xs text-slate-500 dark:text-slate-400">
                {t("users.inviteHint")}
              </span>
            </span>
          </label>
        )}
        <button className={buttonPrimary} disabled={busy}>
          {canInvite && invite ? t("users.createAndInvite") : t("users.create")}
        </button>
        </form>
      </details>

      {historyOn && <details className="surface collection-form">
        <summary><PlusIcon /><span>{t("departments.title")}</span><ChevronDownIcon /></summary>
        <DepartmentsPanel departments={departments} reload={loadDepartments} busy={busy} />
      </details>}

      <div className="space-y-3">
        {users.map((u) => {
          const guard = guarded(u, self, users);
          const inactive = u.active === false;
          return (
            <div key={u.id} className={`${panelClass} p-4 space-y-3 ${inactive ? "opacity-70" : ""}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-900 dark:text-slate-100">{u.username}</span>
                {self && u.id === self.id && (
                  <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[11px] font-medium text-brand-700 dark:bg-brand-900/50 dark:text-brand-200">
                    {t("users.you")}
                  </span>
                )}
                {inactive && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    {t("users.inactive")}
                  </span>
                )}
                <span className="text-sm text-slate-500 dark:text-slate-400">{u.email}</span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <label className="text-xs text-slate-500 dark:text-slate-400">
                  {t("users.role")}
                  <select
                    className={`${inputClass} mt-1 !w-auto py-1.5 text-sm`}
                    value={u.role}
                    disabled={busy || guard !== null}
                    title={guardText(guard)}
                    onChange={(e) => void patch(u.id, { role: e.target.value }, t("users.saved"))}
                  >
                    <option value="user">{t("users.roleUser")}</option>
                    <option value="admin">{t("users.roleAdmin")}</option>
                  </select>
                </label>
                {historyOn && (
                  <label className="text-xs text-slate-500 dark:text-slate-400">
                    {t("departments.userDepartment")}
                    <select
                      className={`${inputClass} mt-1 !w-auto py-1.5 text-sm`}
                      value={u.department_id ?? ""}
                      disabled={busy}
                      onChange={(e) =>
                        void patch(
                          u.id,
                          { department_id: e.target.value ? Number(e.target.value) : null },
                          t("users.saved"),
                        ).then(loadDepartments)
                      }
                    >
                      <option value="">{t("departments.none")}</option>
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                <div className="ml-auto flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={buttonSecondary}
                    disabled={busy || guard !== null}
                    title={guardText(guard)}
                    onClick={() => void patch(u.id, { active: inactive }, t("users.saved"))}
                  >
                    {inactive ? t("users.activate") : t("users.deactivate")}
                  </button>
                  <button
                    type="button"
                    className={buttonSecondary}
                    disabled={busy}
                    onClick={() => {
                      setResetFor(resetFor === u.id ? null : u.id);
                      setResetPassword("");
                    }}
                  >
                    {t("users.resetPassword")}
                  </button>
                  <button
                    type="button"
                    className={buttonSecondary}
                    disabled={busy}
                    title={t("users.clearTwoFactorHint")}
                    onClick={() => setClearTwoFactorTarget(u)}
                  >
                    {t("users.clearTwoFactor")}
                  </button>
                  <button
                    type="button"
                    className={buttonDanger}
                    disabled={busy || guard !== null}
                    title={guardText(guard)}
                    onClick={() => remove(u)}
                  >
                    {t("users.delete")}
                  </button>
                </div>
              </div>

              {resetFor === u.id && (
                <form
                  className="flex flex-wrap items-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void patch(u.id, { password: resetPassword }, t("users.passwordReset"));
                    setResetFor(null);
                    setResetPassword("");
                  }}
                >
                  <div className="min-w-[220px] flex-1">
                    <label className="text-xs text-slate-500 dark:text-slate-400" htmlFor={`reset-${u.id}`}>
                      {t("users.newPasswordFor", { name: u.username })}
                    </label>
                    <input
                      id={`reset-${u.id}`}
                      type="password"
                      className={`${inputClass} mt-1`}
                      value={resetPassword}
                      minLength={8}
                      required
                      onChange={(e) => setResetPassword(e.target.value)}
                    />
                  </div>
                  <button className={buttonPrimary} disabled={busy}>
                    {t("users.resetPasswordDo")}
                  </button>
                </form>
              )}
            </div>
          );
        })}
      </div>

      <ConfirmDialog
        open={clearTwoFactorTarget !== null}
        title={t("users.clearTwoFactor")}
        body={clearTwoFactorTarget ? t("users.clearTwoFactorConfirm", { name: clearTwoFactorTarget.username }) : ""}
        confirmLabel={t("users.clearTwoFactor")}
        onConfirm={() => {
          const target = clearTwoFactorTarget;
          setClearTwoFactorTarget(null);
          if (target) void run(() => api.clearTwoFactorFor(target.id), t("users.twoFactorCleared"));
        }}
        onCancel={() => setClearTwoFactorTarget(null)}
      />
    </div>
  );
}

/**
 * The departments themselves: add, rename, remove.
 *
 * Removing one leaves its people and shipments without a department rather
 * than deleting either — the dialog says so, because "remove" beside a count
 * of shipments reads as if the shipments go too.
 */
function DepartmentsPanel({
  departments,
  reload,
  busy,
}: {
  departments: Department[];
  reload: () => Promise<void>;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState<Department | null>(null);
  const [newName, setNewName] = useState("");
  const [removing, setRemoving] = useState<Department | null>(null);
  const [working, setWorking] = useState(false);

  const act = async (work: () => Promise<unknown>, done: string) => {
    setWorking(true);
    try {
      await work();
      await reload();
      toast.success(done);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setWorking(false);
    }
  };

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    void act(() => api.createDepartment(name.trim()), t("departments.saved")).then(() => setName(""));
  };

  return (
    <div className={`${panelClass} p-5 space-y-4`}>
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {t("departments.title")}
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{t("departments.intro")}</p>
      </div>

      {departments.length === 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400">{t("departments.empty")}</p>
      )}
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {departments.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center gap-2 py-2">
            {renaming?.id === d.id ? (
              <form
                className="flex flex-1 flex-wrap items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(() => api.renameDepartment(d.id, newName.trim()), t("departments.saved")).then(() =>
                    setRenaming(null),
                  );
                }}
              >
                <input
                  className={`${inputClass} !w-auto flex-1 py-1.5 text-sm`}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  aria-label={t("departments.name")}
                  autoFocus
                />
                <button className={buttonPrimary} disabled={working || !newName.trim()}>
                  {t("departments.save")}
                </button>
                <button type="button" className={buttonSecondary} onClick={() => setRenaming(null)}>
                  {t("departments.cancel")}
                </button>
              </form>
            ) : (
              <>
                <span className="font-medium text-slate-900 dark:text-slate-100">{d.name}</span>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t("departments.counts", { users: d.users, shipments: d.shipments })}
                </span>
                <div className="ml-auto flex gap-2">
                  <button
                    type="button"
                    className={buttonSecondary}
                    disabled={busy || working}
                    onClick={() => {
                      setRenaming(d);
                      setNewName(d.name);
                    }}
                  >
                    {t("departments.rename")}
                  </button>
                  <button
                    type="button"
                    className={buttonSecondary}
                    disabled={busy || working}
                    onClick={() => setRemoving(d)}
                  >
                    {t("departments.remove")}
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <div className="min-w-[200px] flex-1">
          <label className="text-xs text-slate-500 dark:text-slate-400" htmlFor="new-department">
            {t("departments.name")}
          </label>
          <input
            id="new-department"
            className={`${inputClass} mt-1`}
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <button className={buttonPrimary} disabled={working || !name.trim()}>
          {t("departments.add")}
        </button>
      </form>

      <ConfirmDialog
        open={removing !== null}
        title={t("departments.remove")}
        body={removing ? t("departments.confirmRemove", { name: removing.name }) : ""}
        confirmLabel={t("departments.remove")}
        onConfirm={() => {
          const target = removing;
          setRemoving(null);
          if (target) void act(() => api.deleteDepartment(target.id), t("departments.removed"));
        }}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}

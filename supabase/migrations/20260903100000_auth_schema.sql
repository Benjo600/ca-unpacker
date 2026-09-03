create type plan_type as enum ('starter', 'pro', 'suspended');

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan plan_type not null default 'starter',
  license_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  org_id uuid not null references public.organizations(id) on delete cascade,
  email text not null,
  role text not null default 'owner' check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  last_active_at timestamptz
);

create table public.devices (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  fingerprint_sha256 text not null,
  label text not null default '',
  app_version text not null default '',
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  active boolean not null default true,
  unique (org_id, fingerprint_sha256)
);

create table public.usage_monthly (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  month text not null,
  files_processed integer not null default 0,
  clients_created integer not null default 0,
  updated_at timestamptz not null default now(),
  unique (org_id, month)
);

create table public.admin_users (
  email text primary key
);

create table public.license_keys (
  id uuid primary key default gen_random_uuid(),
  key_hash text not null unique,
  plan plan_type not null default 'pro',
  org_id uuid references public.organizations(id),
  created_at timestamptz not null default now(),
  redeemed_at timestamptz,
  revoked_at timestamptz
);

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  new_org_id uuid;
  firm_name text;
begin
  firm_name := coalesce(new.raw_user_meta_data->>'firm_name', 'My firm');
  insert into public.organizations (name, plan) values (firm_name, 'starter')
    returning id into new_org_id;
  insert into public.profiles (id, org_id, email, role)
    values (new.id, new_org_id, new.email, 'owner');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

alter table public.organizations enable row level security;
alter table public.profiles enable row level security;
alter table public.devices enable row level security;
alter table public.usage_monthly enable row level security;
alter table public.admin_users enable row level security;
alter table public.license_keys enable row level security;

create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);
create policy "orgs_select_own" on public.organizations
  for select using (
    id in (select org_id from public.profiles where id = auth.uid())
  );
create policy "usage_select_own" on public.usage_monthly
  for select using (
    org_id in (select org_id from public.profiles where id = auth.uid())
  );
create policy "devices_upsert_own" on public.devices
  for all using (
    user_id = auth.uid()
  ) with check (user_id = auth.uid());

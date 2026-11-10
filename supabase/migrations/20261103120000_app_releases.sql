-- Release control plane: drafts, one published release, withdrawal, audit.
-- Only Edge Functions using the service role may call the RPCs below; browser
-- clients can neither read nor write these tables directly.

do $$
begin
  if not exists (select 1 from pg_type where typname = 'release_status') then
    create type release_status as enum ('draft', 'published', 'withdrawn');
  end if;
end
$$;

create table if not exists public.admin_audit_log (
  id bigserial primary key,
  actor_email text not null,
  action text not null,
  entity text not null,
  entity_id text not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.app_releases (
  id uuid primary key default gen_random_uuid(),
  version text not null unique
    check (version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  title text not null check (length(btrim(title)) > 0),
  release_notes text not null default '',
  installer_url text not null check (length(btrim(installer_url)) > 0),
  installer_sha256 text not null check (installer_sha256 ~ '^[0-9a-f]{64}$'),
  installer_size bigint not null check (installer_size > 0),
  status release_status not null default 'draft',
  mandatory boolean not null default false,
  minimum_supported_version text
    check (minimum_supported_version is null
           or minimum_supported_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_by text,
  published_at timestamptz,
  withdrawn_by text,
  withdrawn_at timestamptz
);

create unique index if not exists app_releases_one_published
  on public.app_releases (status)
  where status = 'published';

alter table public.app_releases enable row level security;
alter table public.admin_audit_log enable row level security;

revoke all on public.app_releases from anon, authenticated;
revoke all on public.admin_audit_log from anon, authenticated;
revoke all on sequence public.admin_audit_log_id_seq from anon, authenticated;

create or replace function public.admin_audit(
  p_actor text,
  p_action text,
  p_entity_id text,
  p_detail jsonb
) returns void
language sql
security definer
set search_path = public
as $$
  insert into public.admin_audit_log (actor_email, action, entity, entity_id, detail)
  values (coalesce(nullif(btrim(p_actor), ''), 'unknown'), p_action, 'app_release', p_entity_id, coalesce(p_detail, '{}'::jsonb));
$$;

revoke all on function public.admin_audit(text, text, text, jsonb) from public, anon, authenticated;

create or replace function public.admin_save_release(
  p_id uuid,
  p_version text,
  p_title text,
  p_release_notes text,
  p_installer_url text,
  p_installer_sha256 text,
  p_installer_size bigint,
  p_mandatory boolean,
  p_minimum_supported_version text,
  p_actor text
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
  v_status release_status;
begin
  if p_version is null or p_version !~ '^[0-9]+\.[0-9]+\.[0-9]+$' then
    raise exception 'Version must look like 1.2.3' using errcode = '22023';
  end if;
  if p_installer_sha256 is null or p_installer_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'Checksum must be 64 lowercase hex characters' using errcode = '22023';
  end if;
  if p_installer_size is null or p_installer_size <= 0 then
    raise exception 'Installer size must be positive' using errcode = '22023';
  end if;
  if p_title is null or length(btrim(p_title)) = 0 then
    raise exception 'Title is required' using errcode = '22023';
  end if;
  if p_installer_url is null or length(btrim(p_installer_url)) = 0 then
    raise exception 'Installer URL is required' using errcode = '22023';
  end if;

  if p_id is null then
    insert into public.app_releases (
      version, title, release_notes, installer_url, installer_sha256,
      installer_size, mandatory, minimum_supported_version, created_by
    ) values (
      p_version, btrim(p_title), coalesce(p_release_notes, ''), btrim(p_installer_url),
      lower(p_installer_sha256), p_installer_size, coalesce(p_mandatory, false),
      nullif(btrim(coalesce(p_minimum_supported_version, '')), ''), coalesce(nullif(btrim(p_actor), ''), 'unknown')
    ) returning id into v_id;
  else
    select status into v_status from public.app_releases where id = p_id for update;
    if not found then
      raise exception 'Release not found' using errcode = 'P0002';
    end if;
    if v_status <> 'draft' then
      raise exception 'Only draft releases can be edited' using errcode = 'P0001';
    end if;
    update public.app_releases set
      version = p_version,
      title = btrim(p_title),
      release_notes = coalesce(p_release_notes, ''),
      installer_url = btrim(p_installer_url),
      installer_sha256 = lower(p_installer_sha256),
      installer_size = p_installer_size,
      mandatory = coalesce(p_mandatory, false),
      minimum_supported_version = nullif(btrim(coalesce(p_minimum_supported_version, '')), ''),
      updated_at = now()
    where id = p_id;
    v_id := p_id;
  end if;

  perform public.admin_audit(
    p_actor,
    case when p_id is null then 'release_draft_created' else 'release_draft_updated' end,
    v_id::text,
    jsonb_build_object('version', p_version, 'mandatory', coalesce(p_mandatory, false))
  );
  return v_id;
end;
$$;

create or replace function public.admin_publish_release(
  p_id uuid,
  p_actor text
) returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_status release_status;
  v_other record;
begin
  select status into v_status from public.app_releases where id = p_id for update;
  if not found then
    raise exception 'Release not found' using errcode = 'P0002';
  end if;
  if v_status <> 'draft' then
    raise exception 'Only draft releases can be published' using errcode = 'P0001';
  end if;

  for v_other in
    select id, version from public.app_releases
    where status = 'published' and id <> p_id
    for update
  loop
    update public.app_releases set
      status = 'withdrawn',
      withdrawn_by = coalesce(nullif(btrim(p_actor), ''), 'unknown'),
      withdrawn_at = now(),
      updated_at = now()
    where id = v_other.id;
    perform public.admin_audit(
      p_actor, 'release_auto_withdrawn', v_other.id::text,
      jsonb_build_object('version', v_other.version, 'reason', 'newer release published')
    );
  end loop;

  update public.app_releases set
    status = 'published',
    published_by = coalesce(nullif(btrim(p_actor), ''), 'unknown'),
    published_at = now(),
    updated_at = now()
  where id = p_id;

  perform public.admin_audit(
    p_actor, 'release_published', p_id::text,
    (select jsonb_build_object('version', version, 'mandatory', mandatory) from public.app_releases where id = p_id)
  );
end;
$$;

create or replace function public.admin_withdraw_release(
  p_id uuid,
  p_actor text
) returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_status release_status;
  v_version text;
begin
  select status, version into v_status, v_version
  from public.app_releases where id = p_id for update;
  if not found then
    raise exception 'Release not found' using errcode = 'P0002';
  end if;
  if v_status <> 'published' then
    raise exception 'Only a published release can be withdrawn' using errcode = 'P0001';
  end if;
  update public.app_releases set
    status = 'withdrawn',
    withdrawn_by = coalesce(nullif(btrim(p_actor), ''), 'unknown'),
    withdrawn_at = now(),
    updated_at = now()
  where id = p_id;
  perform public.admin_audit(
    p_actor, 'release_withdrawn', p_id::text, jsonb_build_object('version', v_version)
  );
end;
$$;

revoke all on function public.admin_save_release(uuid, text, text, text, text, text, bigint, boolean, text, text) from public, anon, authenticated;
revoke all on function public.admin_publish_release(uuid, text) from public, anon, authenticated;
revoke all on function public.admin_withdraw_release(uuid, text) from public, anon, authenticated;

grant execute on function public.admin_save_release(uuid, text, text, text, text, text, bigint, boolean, text, text) to service_role;
grant execute on function public.admin_publish_release(uuid, text) to service_role;
grant execute on function public.admin_withdraw_release(uuid, text) to service_role;

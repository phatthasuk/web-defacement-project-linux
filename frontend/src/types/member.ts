export type MemberRole = 'admin' | 'operator';
export type MemberStatus = 'pending' | 'active' | 'suspended' | 'rejected';
export type RegistrationStatus = 'pending' | 'approved' | 'rejected';

export type Member = {
  id: number;
  username: string;
  display_name: string;
  role: MemberRole;
  is_active: boolean;
  status: MemberStatus;
  registration_status: RegistrationStatus;
  registration_at: string;
  registration_reviewed_at?: string | null;
  registration_reviewed_by?: number | null;
  registration_rejection_reason?: string | null;
  last_login_at: string | null;
  must_change_password: boolean;
  assigned_website_count: number;
  created_at?: string;
};

export type PaginatedMembers = {
  items: Member[];
  total: number;
  pending_count: number;
  limit: number;
  offset: number;
};

export type TargetAssignee = {
  id: number;
  username: string;
  display_name: string;
  is_active: boolean;
};

export type MemberWebsiteTag = {
  id: string;
  name: string;
  color_key: string;
};

export type MemberWebsite = {
  id: string;
  name: string;
  url: string;
  is_active: boolean;
  tags: MemberWebsiteTag[];
  assignees?: TargetAssignee[];
};

export type MemberWebsitesCounts = {
  all: number;
  unassigned: number;
  assigned: number;
};

export type PaginatedMemberWebsites = {
  items: MemberWebsite[];
  total: number;
  counts: MemberWebsitesCounts;
  limit: number;
  offset: number;
};

export type MemberWebsitesList = {
  items: MemberWebsite[];
  total: number;
  limit: number;
  offset: number;
};

export type MemberCreatePayload = {
  username: string;
  display_name: string;
  temporary_password: string;
};

export type MemberUpdatePayload = {
  display_name?: string;
  is_active?: boolean;
};

export type RejectMemberPayload = {
  reason?: string;
};

export type ResetPasswordPayload = {
  temporary_password: string;
};

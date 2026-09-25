import { api } from './client'
import type { Schema } from './types'

export type Member = Schema<'MemberOut'>
export type Invitation = Schema<'InvitationOut'>
export type InvitationCreated = Schema<'InvitationCreatedOut'>
export type Role = Member['role']
export type AssignableRole = NonNullable<Schema<'MemberUpdate'>['role']>
export const ASSIGNABLE_ROLES: AssignableRole[] = ['Admin', 'Manager', 'Agent', 'Viewer']

export const teamApi = {
  members: () => api.get<Member[]>('/api/team/members'),
  updateMember: (id: string, patch: Schema<'MemberUpdate'>) => api.patch<Member>(`/api/team/members/${id}`, patch),
  removeMember: (id: string) => api.delete<void>(`/api/team/members/${id}`),
  transferOwnership: (userId: string) => api.post<Member>('/api/team/transfer-ownership', { user_id: userId }),
  invitations: () => api.get<Invitation[]>('/api/team/invitations'),
  invite: (email: string, role: AssignableRole) =>
    api.post<InvitationCreated>('/api/team/invitations', { email, role } satisfies Schema<'InvitationCreate'>),
  revokeInvitation: (id: string) => api.delete<void>(`/api/team/invitations/${id}`),
}

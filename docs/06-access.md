---
title: Access and accounts
group: Using ThemisForge
summary: How people get an account: an administrator, access requests and invite links.
---

# Access and accounts

ThemisForge is **invite only**. There is no open sign up.

## The administrator

The first account created on a new installation becomes the **administrator**. Only the administrator sees
**Settings** and **Access** in the sidebar, and only the administrator manages keys, Docker and other people's access.
Every account after that is a regular user.

## Asking for access

On the sign in screen, anyone can choose **Request access** and fill in their name, email and a reason. The reason is
prefilled with a short collaboration message that you can edit.

For privacy the form always answers "Request sent", whether or not that email already has an account. Only one request
per email stays pending, and the number of pending requests is capped, so the form cannot be used to probe accounts or
flood the inbox.

## Handling requests

Open **Access** in the sidebar. A badge on the sidebar item shows how many requests are waiting.

- **Approve** creates an **invite link** for that email address.
- **Deny** closes the request.

Handled requests stay listed under *Earlier requests*.

## Invite links

An invite link is personal and **works once**. It expires after **7 days**.

1. Approve a request, or use **Invite someone** and enter an email address.
2. Copy the link from the dialog and send it to the person yourself.
3. They open it, see their email address, choose a name and a password, and are signed in.

A few things worth knowing:

- The link is shown **once**. ThemisForge keeps only a hash of it, so it cannot show it again. If it is lost, create a
  new invite for the same address: the new one replaces the old one.
- You can **revoke** an open invite at any time.
- Opening an expired, used or revoked link shows an *Invite not valid* page.
- ThemisForge does not send email yet, so links are shared by hand.

## What other users can do

Regular users can create and manage their own projects and tasks. Projects are **private** to the person who created
them. Settings, keys and access management stay with the administrator.

## Sessions and passwords

Signing in sets a session cookie that lasts seven days. Passwords are stored as Argon2 hashes and must be at least
8 characters. If you serve ThemisForge over HTTPS, enable secure cookies, see
[Install and operations](/docs/operations).

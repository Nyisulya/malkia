import json
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Customer, JobDocument, JobShipment


class DocumentDirectUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='document-uploader',
            password='test-password',
            is_staff=True,
        )
        self.client.force_login(self.user)
        customer = Customer.objects.create(company_name='Upload Test Client')
        self.job = JobShipment.objects.create(
            job_number='CF/2026/9999',
            customer=customer,
            bl_number='UPLOADTEST',
        )

    def upload_payload(self):
        return {
            'files': [{
                'name': 'signed-tra.pdf',
                'size': 2048,
                'content_type': 'application/pdf',
                'document_type': 'TRA_AUTH_SIGNED',
                'title': 'Signed TRA Authorization',
            }],
        }

    def request_upload_urls(self, payload=None):
        with patch('core.storage_backends.get_r2_config', return_value={'is_configured': True}), patch(
            'core.storage_backends.generate_presigned_upload_url',
            return_value='https://r2.example.test/presigned-upload',
        ):
            return self.client.post(
                reverse('create_document_upload_urls', args=[self.job.id]),
                data=json.dumps(payload or self.upload_payload()),
                content_type='application/json',
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

    def complete_upload(self, upload):
        return self.client.post(
            reverse('upload_documents_batch', args=[self.job.id]),
            data=json.dumps({
                'documents': [{
                    'object_key': upload['object_key'],
                    'completion_token': upload['completion_token'],
                }],
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_direct_upload_creates_r2_document_without_local_file_upload(self):
        response = self.request_upload_urls()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')

        upload = payload['uploads'][0]
        self.assertTrue(upload['object_key'].startswith('malkia_files/'))
        self.assertEqual(upload['content_type'], 'application/pdf')

        completed = self.complete_upload(upload)
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()['uploaded'], 1)

        document = JobDocument.objects.get(job=self.job)
        self.assertEqual(document.file.name, upload['object_key'])
        self.assertEqual(document.document_type, 'TRA_AUTH_SIGNED')
        self.job.refresh_from_db()
        self.assertTrue(self.job.doc_intake_finalized)
        self.assertEqual(self.job.documentation_officer, self.user)

    def test_direct_upload_replaces_single_slot_document(self):
        JobDocument.objects.create(
            job=self.job,
            document_type='TRA_AUTH_SIGNED',
            title='Old TRA letter',
            file='malkia_files/2026/old-tra.pdf',
        )

        upload = self.request_upload_urls().json()['uploads'][0]
        response = self.complete_upload(upload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(JobDocument.objects.filter(job=self.job).count(), 1)
        self.assertEqual(JobDocument.objects.get(job=self.job).file.name, upload['object_key'])

    def test_completion_rejects_tampered_object_key(self):
        upload = self.request_upload_urls().json()['uploads'][0]
        upload['object_key'] = 'malkia_files/2026/another-job.pdf'

        response = self.complete_upload(upload)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(JobDocument.objects.filter(job=self.job).exists())

    def test_unconfigured_r2_requests_vps_fallback(self):
        with patch('core.storage_backends.get_r2_config', return_value={'is_configured': False}):
            response = self.client.post(
                reverse('create_document_upload_urls', args=[self.job.id]),
                data=json.dumps(self.upload_payload()),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'fallback')

    def test_vps_fallback_still_saves_multipart_upload(self):
        uploaded_file = SimpleUploadedFile(
            'fallback-tra.pdf',
            b'%PDF-1.4\nfallback-test',
            content_type='application/pdf',
        )
        field = JobDocument._meta.get_field('file')
        with tempfile.TemporaryDirectory() as media_root, patch.object(
            field,
            'storage',
            FileSystemStorage(location=media_root),
        ):
            response = self.client.post(
                reverse('upload_documents_batch', args=[self.job.id]),
                data={
                    'files': [uploaded_file],
                    'document_types': ['TRA_AUTH_SIGNED'],
                    'titles': ['Fallback TRA letter'],
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
            self.assertEqual(response.status_code, 200)
            document = JobDocument.objects.get(job=self.job)
            self.assertTrue(field.storage.exists(document.file.name))

    def test_upload_url_request_rejects_unsupported_file_type(self):
        payload = self.upload_payload()
        payload['files'][0]['name'] = 'document.exe'

        response = self.request_upload_urls(payload)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(JobDocument.objects.filter(job=self.job).exists())


class NotificationDisabledTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='staff-test',
            password='test-password',
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(
            company_name='Client Test Ltd',
            email='client@example.com',
            phone='0712345678',
        )
        self.job = JobShipment.objects.create(
            job_number='CF/2026/8888',
            customer=self.customer,
            bl_number='BLNOTIFTEST',
        )

    def test_email_and_sms_services_return_disabled_without_network_calls(self):
        from core.email_service import (
            send_resend_email,
            send_nextsms_sms,
            send_smsgate_sms,
            send_stage_update_email,
            notify_client_milestone,
            send_declarer_intake_notification,
        )

        ok, msg = send_resend_email('client@example.com', 'Subject', '<p>Body</p>')
        self.assertFalse(ok)
        self.assertIn('umezimwa', msg)

        ok, msg = send_nextsms_sms('0712345678', 'Test SMS')
        self.assertFalse(ok)
        self.assertIn('umezimwa', msg)

        ok, msg = send_smsgate_sms('0712345678', 'Test SMS')
        self.assertFalse(ok)
        self.assertIn('umezimwa', msg)

        ok, msg = send_stage_update_email(self.job, 1)
        self.assertFalse(ok)
        self.assertIn('umezimwa', msg)

        notif_res = notify_client_milestone(self.job, 'DOCS_RECEIVED')
        self.assertFalse(notif_res['email_ok'])
        self.assertFalse(notif_res['sms_ok'])

        ok, msg = send_declarer_intake_notification(self.job, self.user)
        self.assertFalse(ok)
        self.assertIn('umezimwa', msg)

    def test_send_job_stage_email_action_view_redirects_with_info_message(self):
        response = self.client.post(
            reverse('send_job_stage_email', args=[self.job.id]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages_list = list(response.context['messages'])
        self.assertTrue(any('umezimwa' in str(m) for m in messages_list))


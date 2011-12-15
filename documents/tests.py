"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

"""
from django.test import TestCase
from django.conf import settings
from geonode.maps.models import Map, MapLayer
from documents.models import Document
import documents.views
import geonode.core
from django.test.client import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
import StringIO
from django.contrib.auth.models import User, AnonymousUser
import json

LOGIN_URL = settings.SITEURL + "accounts/login/"

imgfile = StringIO.StringIO('GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00'
								'\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
def create_document():
	f = SimpleUploadedFile('test_img_file.gif', imgfile.read(), 'image/gif')
	m, __ = Map.objects.get_or_create(id=1, title='foo', projection='4326', zoom=2, center_x=0, center_y=0,
									  owner=User.objects.get(username='bobby'))
	for ord, lyr in enumerate(settings.MAP_BASELAYERS):
		MapLayer.objects.from_viewer_config(
			map=m,
			layer=lyr,
			source=settings.MAP_BASELAYERSOURCES[lyr["source"]],
			ordering=ord
		).save()
	m.set_default_permissions()
	superuser = User.objects.get(pk=2)
	c, created = Document.objects.get_or_create(id=1, file=f,owner=superuser)
	c.set_default_permissions()
	c.maps.add(m)
	return c, created

class EventsTest(TestCase):
	fixtures = ['test_data.json',]
	
	def test_map_details(self):
		"""/maps/1 -> Test accessing the detail view of a map"""
		create_document()
		map = Map.objects.get(id=1)
		c = Client()
		response = c.get("/maps/%s" % str(map.id))
		self.assertEquals(response.status_code, 200)

	def test_document_details(self):
		"""/documents/1 -> Test accessing the detail view of a document"""
		create_document()
		document = Document.objects.get(id=1)
		c = Client()
		response = c.get("/documents/%s" % str(document.id))
		self.assertEquals(response.status_code, 200)

	def test_access_document_upload_form(self):
		"""Test the form page is returned correctly via GET request /documents/upload"""
		c = Client()
		log = c.login(username='bobby', password='bob')
		self.assertTrue(log)
		response = c.get("/documents/upload")
		self.assertTrue('Add document' in response.content)

	def test_document_isuploaded(self):
		"""/documents/upload -> Test uploading a document"""
		f = SimpleUploadedFile('test_img_file.gif', imgfile.read(), 'image/gif')
		m, __ = Map.objects.get_or_create(id=1, title='foo', projection='4326', zoom=2, center_x=0, center_y=0,
										  owner=User.objects.get(username='bobby'))
		c = Client()
		
		c.login(username='admin', password='admin')
		response = c.post("/documents/upload", {'file': f, 'title': 'uploaded_document', 'map': m.id},
						  follow=True)
		self.assertEquals(response.status_code, 200)

	def test_newmap_template(self):
		"""
		Test if the newmap template is returned correctly
		"""
		c = Client()
		response = c.get('/documents/newmap')
		self.assertEquals(response.status_code, 200)

	def test_document_creation(self):
		"""
		Test if a document is created properly
		"""
		f = SimpleUploadedFile('test_img_file.gif', imgfile.read(), 'image/gif')
		m, __ = Map.objects.get_or_create(id=1, title='foo', projection='4326', zoom=2, center_x=0, center_y=0,
									  owner=User.objects.get(username='bobby'))
		m.set_default_permissions()
		d,created = Document.objects.get_or_create(id=1, file=f)
		d.maps.add(m)
		self.assertTrue(created)
		
	# Permissions Tests

	# Users
	# - admin (pk=2)
	# - bobby (pk=1)

	# Inherited
	# - LEVEL_NONE = _none

	# Layer
	# - LEVEL_READ = document_read
	# - LEVEL_WRITE = document_readwrite
	# - LEVEL_ADMIN = document_admin
	

	# FIXME: Add a comprehensive set of permissions specifications that allow us 
	# to test as many conditions as is possible/necessary
	
	# If anonymous and/or authenticated are not specified, 
	# should set_layer_permissions remove any existing perms granted??
	
	perm_spec = {"anonymous":"_none","authenticated":"_none","users":[["bobby","document_readwrite"]]}
	
	def test_set_document_permissions(self):
		"""Verify that the set_document_permissions view is behaving as expected
		"""
		create_document()
		# Get a document to work with
		document = Document.objects.all()[0]

		# Save the Layers current permissions
		current_perms = document.get_all_level_info() 
	   
		# Set the Permissions
		documents.views.set_document_permissions(document, self.perm_spec)

		# Test that the Permissions for ANONYMOUS_USERS and AUTHENTICATED_USERS were set correctly		  
		self.assertEqual(document.get_gen_level(geonode.core.models.ANONYMOUS_USERS), document.LEVEL_NONE) 
		self.assertEqual(document.get_gen_level(geonode.core.models.AUTHENTICATED_USERS), document.LEVEL_NONE)

		# Test that previous permissions for users other than ones specified in
		# the perm_spec (and the document owner) were removed
		users = [n for (n, p) in self.perm_spec['users']]
		levels = document.get_user_levels().exclude(user__username__in = users + [document.owner])
		self.assertEqual(len(levels), 0)
	   
		# Test that the User permissions specified in the perm_spec were applied properly
		for username, level in self.perm_spec['users']:
			user = geonode.maps.models.User.objects.get(username=username)
			self.assertEqual(document.get_user_level(user), level)	  

	def test_ajax_document_permissions(self):
		"""Verify that the ajax_document_permissions view is behaving as expected
		"""
		
		# Setup some document names to work with 
		create_document()
		document_id = Document.objects.all()[0].id
		invalid_document_id = 5
		
		c = Client()

		# Test that an invalid layer.typename is handled for properly
		response = c.post("/documents/%s/ajax-permissions" % invalid_document_id, 
							data=json.dumps(self.perm_spec),
							content_type="application/json")
		self.assertEquals(response.status_code, 404) 

		# Test that POST is required
		response = c.get("/documents/%s/ajax-permissions" % document_id)
		self.assertEquals(response.status_code, 405)
		
		# Test that a user is required to have maps.change_layer_permissions

		# First test un-authenticated
		response = c.post("/documents/%s/ajax-permissions" % document_id, 
							data=json.dumps(self.perm_spec),
							content_type="application/json")
		self.assertEquals(response.status_code, 401) 

		# Next Test with a user that does NOT have the proper perms
		logged_in = c.login(username='bobby', password='bob')
		self.assertEquals(logged_in, True) 
		response = c.post("/documents/%s/ajax-permissions" % document_id, 
							data=json.dumps(self.perm_spec),
							content_type="application/json")
		self.assertEquals(response.status_code, 401) 

		# Login as a user with the proper permission and test the endpoint
		logged_in = c.login(username='admin', password='admin')
		self.assertEquals(logged_in, True)
		response = c.post("/documents/%s/ajax-permissions" % document_id, 
							data=json.dumps(self.perm_spec),
							content_type="application/json")

		# Test that the method returns 200		   
		self.assertEquals(response.status_code, 200)
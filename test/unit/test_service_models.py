# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from dns.resolver import NXDOMAIN
from future.moves.urllib.parse import urlparse, parse_qs
from nose_parameterized import parameterized
from requests.exceptions import HTTPError

from spam_lists.exceptions import UnathorizedAPIKeyError, UnknownCodeError, \
InvalidURLError, InvalidHostError
from spam_lists.service_models import DNSBL, GoogleSafeBrowsing, \
HostCollection, HostList, HpHosts
from spam_lists.structures import AddressListItem
from test.compat import unittest, Mock, MagicMock, patch, lru_cache
from test.unit.common_definitions import UrlTesterTestBase, \
TestFunctionDoesNotHandleProvider


class UrlTesterTest(UrlTesterTestBase):
    ''' A class providing pre-generated tests for classes
    having any_match, filter_matching and lookup_matching
    methods '''
    
    classification = set(['TEST'])
    
    valid_url_input = [
                           ('ipv4_url', ['http://55.44.33.21']),
                           ('hostname_url', ['https://abc.com']),
                           ('ipv6_url', ['http://[2001:ddd:ccc:111::33]'])
                           ]
    
    valid_url_list_input = [
                             ('no_matching_url', []),
                             ('two_urls', ['http://55.44.33.21', 'https://abc.com'])
                             ]+valid_url_input
                             
    @parameterized.expand([
                           ('any_match'),
                           ('lookup_matching'),
                           ('filter_matching')
                           ])
    @patch('spam_lists.validation.is_valid_url')
    def test_invalid_url_error_is_raised_by(self, function_name, is_valid_url_mock):
        invalid_url = 'http://invalid.url.com'
        is_valid_url_mock.side_effect = lambda u: u != invalid_url
        
        function = getattr(self.tested_instance, function_name)
        with self.assertRaises(InvalidURLError):
            function(self.valid_urls + [invalid_url])
    
    @parameterized.expand(valid_url_input)
    def test_any_match_returns_true_for(self, _, matching_urls):
        
        self._test_any_match_returns_true_for(matching_urls)
        
    @parameterized.expand(valid_url_list_input)
    def test_lookup_matching_for(self, _, matching_urls):
        
        self._test_lookup_matching_for(matching_urls)
        
    @parameterized.expand(valid_url_list_input)
    def test_filter_matching_for(self, _, matching_urls):
        self._test_filter_matching_for(matching_urls)
    
    def _get_expected_items(self, values):
        item = lambda i: AddressListItem(i, self.tested_instance,
                                             self.classification)
        return [item(v) for v in values]
    
def get_hosts(urls):
    
    return [urlparse(u).hostname for u in urls]

class HostListTestBase(UrlTesterTest):
    ''' A common test case for all classes that represent
    a host list stored locally or by a remote service '''
    
    valid_host_input = [
                        ('ipv4', '255.0.120.1'),
                        ('hostname', 'test.pl'),
                        ('ipv6', '2001:ddd:ccc:111::33')
                        ]
    
    def _set_matching_urls(self, urls):
        self._set_matching_hosts(get_hosts(urls))
        
    def _get_expected_items_for_urls(self, urls):
        return self._get_expected_items(get_hosts(urls))
    
    def _test_function_does_not_handle_invalid_host_error(self, function, arg):
        self._test_function_does_not_handle(InvalidHostError,
                                            self.host_factory_mock,
                                            function,
                                            arg
                                            )
        
    def _get_return_value_for_unsupported_host(self, function):
        unsupported_host = 'unsupported.com'
        self.host_factory_mock.side_effect = InvalidHostError
        
        return function(unsupported_host)
        
    def test_contains_returns_false_for_unsupported_host(self):
        actual = self._get_return_value_for_unsupported_host(
                                                             self.tested_instance.__contains__
                                                             )
        self.assertFalse(actual)
        
    def test_lookup_returns_none_for_unsupported_host(self):
        actual = self._get_return_value_for_unsupported_host(
                                                             self.tested_instance.lookup
                                                             )
        self.assertIsNone(actual)
        
    @patch('spam_lists.validation.is_valid_host')
    def _test_function_raises_invalid_host_error(self, function, is_valid_host_mock):
        invalid_host = 'invalid.com'
        is_valid_host_mock.side_effect = lambda h: h != invalid_host
        
        with self.assertRaises(InvalidHostError):
            function(invalid_host)
        
    @parameterized.expand([
                           ('__contains__'),
                           ('lookup')
                           ])
    def test_invalid_host_error_is_raised_by(self, function_name):
        
        function = getattr(self.tested_instance, function_name)
        self._test_function_raises_invalid_host_error(function)
        
    @parameterized.expand(valid_host_input)
    def test_contains_for_listed(self, _, value):
        self._set_matching_hosts([value])
        self.assertTrue(value in self.tested_instance)
            
    @parameterized.expand(valid_host_input)
    def test_contains_for_not_listed(self, _, value):
        self.assertFalse(value in self.tested_instance)
                
    @parameterized.expand(valid_host_input)
    def test_lookup_for_listed(self, _, value):
        expected = self._get_expected_items([value])[0]
        self._set_matching_hosts([value])
        self.assertEqual(self.tested_instance.lookup(value), expected)
          
    @parameterized.expand(valid_host_input)  
    def test_lookup_for_not_listed(self, _, value):
        self.assertIsNone(self.tested_instance.lookup(value))


@lru_cache()
def host_list_host_factory(h):
    host_object = MagicMock()
    host_object.to_unicode.return_value = h
    return host_object


class HostListTest(HostListTestBase, unittest.TestCase):
    
    def setUp(self):
        self.listed_hosts = []
        self.host_factory_mock = Mock()
        self.host_factory_mock.side_effect = host_list_host_factory
        self.tested_instance = HostList(self.host_factory_mock)
        
        self._contains_patcher = patch('spam_lists.service_models.HostList._contains')
        self._contains_mock = self._contains_patcher.start()
        self._contains_mock.side_effect = lambda h: h in self.listed_hosts
        
        self._get_match_and_classification_patcher = patch('spam_lists.service_models.HostList._get_match_and_classification')
        self._get_match_and_classification_mock = self._get_match_and_classification_patcher.start()
        
        def _get_match_and_classification(h):
            if h in self.listed_hosts:
                return h, self.classification
            return None, None
        
        self._get_match_and_classification_mock.side_effect = _get_match_and_classification
        
    def tearDown(self):
        self._contains_patcher.stop()
        self._get_match_and_classification_patcher.stop()
        
    def _set_matching_hosts(self, matching_hosts):
        
        self.listed_hosts = [self.host_factory_mock(mh) for mh in matching_hosts]


def create_dns_query_function(expected_query_names):
    def dns_query(query_name):
            if query_name in expected_query_names:
                dns_answer_mock = Mock()
                dns_answer_mock.to_text.return_value = '121.0.0.1'
                return [dns_answer_mock]
            raise NXDOMAIN
    return dns_query
        
class DNSBLTest(
                HostListTestBase,
                TestFunctionDoesNotHandleProvider,
                unittest.TestCase
                ):
     
    query_domain_str = 'test.query.domain'
     
    def setUp(self):
         
        self.classification_map = MagicMock()
        self.classification_map.__getitem__.return_value = self.classification
         
        self.host_factory_mock = Mock()
        self.host_factory_mock.side_effect = host_list_host_factory
         
        self.tested_instance = DNSBL('test_service', self.query_domain_str, 
                                   self.classification_map, self.host_factory_mock)
         
        self.dns_query_patcher = patch('spam_lists.service_models.query')
        self.dns_query_mock = self.dns_query_patcher.start()
        self.dns_query_mock.side_effect = create_dns_query_function([])
         
    def tearDown(self):
         
        self.dns_query_patcher.stop()
         
    def _set_matching_hosts(self, hosts):
         
        host_objects = [self.host_factory_mock(h) for h in hosts]
        expected_query_names = [h.relative_domain.derelativize() 
                                for h in host_objects]
        self.dns_query_mock.side_effect = create_dns_query_function(expected_query_names)
        
    def _test_function_does_not_handle_unknown_code_error(self, function, *args, **kwargs):
        self._test_function_does_not_handle(
                                            UnknownCodeError,
                                            self.classification_map.__getitem__,
                                            function,
                                            *args,
                                            **kwargs
                                            )
        
    def test_lookup_does_not_handle_unknown_code_error(self):
        
        host = 'hostwithunknowncode.com'
        self._set_matching_hosts([host])
        self._test_function_does_not_handle_unknown_code_error(
                                                               self.tested_instance.lookup,
                                                               host
                                                               )
        
    def test_lookup_matching_does_not_handle_unknown_code_error(self):
        
        url = 'http://hostwithunknowncode.com'
        self._set_matching_hosts([urlparse(url).hostname])
        
        self._test_function_does_not_handle_unknown_code_error(
                                                               self.tested_instance.lookup_matching,
                                                               [url]
                                                               )


def create_hp_hosts_get(classification, listed_hosts):
    class_str = ','.join(classification)
    def hp_hosts_get(url):
        query_string = urlparse(url).query
        query_data = parse_qs(query_string)
        
        content = 'Not Listed'
        host = query_data['s'][0]
        
        if host in listed_hosts:
            content = 'Listed,{}'.format(class_str)
            
        response = Mock()
        response.text = content
        return response
    return hp_hosts_get

class HpHostsTest(HostListTestBase, unittest.TestCase):
    
    valid_ipv6 = '2001:ddd:ccc:111::33'
    
    @classmethod
    def setUpClass(cls):
         
        cls.tested_instance = HpHosts('spambl_test_suite')
        
    def _set_up_get_mock(self):
        self.get_patcher = patch('spam_lists.service_models.get')
        self.get_mock = self.get_patcher.start()
        self.get_mock.side_effect = create_hp_hosts_get(self.classification, [])
        
    def setUp(self):
         
        self.listed_hosts = []
        
        self._set_up_get_mock()
        
        self.host_factory_mock = Mock()
        
        self.tested_instance = HpHosts('spambl_test_suite')
        self.tested_instance._host_factory = self.host_factory_mock
         
        self.host_factory_mock.side_effect = host_list_host_factory
         
        self.is_valid_url_patcher = patch('spam_lists.validation.is_valid_url')
        self.is_valid_url_mock = self.is_valid_url_patcher.start()
         
    def tearDown(self):
        self.get_patcher.stop()
        self.is_valid_url_patcher.stop()
         
    def _set_matching_hosts(self, hosts):
        self.get_mock.side_effect = create_hp_hosts_get(self.classification, hosts)
        
class GoogleSafeBrowsingTest(UrlTesterTest, unittest.TestCase):
    
    def _get_expected_items_for_urls(self, urls):
        return self._get_expected_items(urls)
    
    @classmethod
    def setUpClass(cls):
        cls.tested_instance = GoogleSafeBrowsing('test_client', '0.1', 'test_key')
        
    def _set_up_post_mock(self):
        
        def post(_, body):
            response = Mock()
            if self._expecting_unathorized_api_key_error:
                response.status_code = 401
                response.raise_for_status.side_effect = HTTPError
                
            else:
                urls = body.splitlines()[1:]
                classes = ['ok' if u not in self._spam_urls else 
                       ','.join(self.classification) for u in urls]
                response.text = '\n'.join(classes)
                code = 200 if self._spam_urls else 204
                response.status_code = code
            
            return response
        
        self.post_patcher = patch('spam_lists.service_models.post')
        self.mocked_post = self.post_patcher.start()
        self.mocked_post.side_effect = post
        
    def setUp(self):
        self._spam_urls = []
        self._expecting_unathorized_api_key_error = False
        
        self._set_up_post_mock()
        
    def tearDown(self):
        self.post_patcher.stop()
        
    def _set_matching_urls(self, urls):
        self._spam_urls = urls
        
    def _test_for_unathorized_api_key(self, function):
        
        self._expecting_unathorized_api_key_error = True
        
        self.assertRaises(UnathorizedAPIKeyError, function, self.valid_urls)
        
    def test_any_match_for_unathorized_api_key(self):
        
        self._test_for_unathorized_api_key(self.tested_instance.any_match)
        
    def test_lookup_matching_for_unathorized_api_key(self):
        
        function = lambda u: list(self.tested_instance.lookup_matching(u))
        self._test_for_unathorized_api_key(function)
        
def host_collection_host_factory(h):
            host_object = host_list_host_factory(h)
            host_object.is_subdomain.return_value = False
            host_object.__eq__.return_value = False
            
            test = lambda h2: host_object.to_unicode() == h2.to_unicode()
            host_object.__eq__.side_effect = test
            host_object.is_subdomain.side_effect = test
                
            return host_object
        
class HostCollectionTest(
                         HostListTestBase,
                         TestFunctionDoesNotHandleProvider,
                         unittest.TestCase
                         ):
     
    valid_urls = ['http://test.com', 'http://127.33.22.11']
    
    def setUp(self):
         
        self.host_factory_patcher = patch('spam_lists.service_models.hostname_or_ip')
        self.host_factory_mock = self.host_factory_patcher.start()
         
        self.host_factory_mock.side_effect = lru_cache()(host_collection_host_factory)
         
        self.classification = set(['test_classification'])
        self.tested_instance = HostCollection('test_host_collection',
                                              self.classification)
         
    def tearDown(self):
        self.host_factory_patcher.stop()
        
    def test_add_does_not_handle_value_error(self):
        function = self.tested_instance.add
        
        self._test_function_does_not_handle_invalid_host_error(function, 'invalidhost.com')
         
    @parameterized.expand(HostListTestBase.valid_host_input)
    def test_add_for_valid(self, _, value):
         
        self.tested_instance.add(value)
         
        in_host_collection = self.host_factory_mock(value) in self.tested_instance.hosts
         
        self.assertTrue(in_host_collection)
         
    def _set_matching_hosts(self, hosts):
        self.tested_instance.hosts = [self.host_factory_mock(h) for h in hosts]
        


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
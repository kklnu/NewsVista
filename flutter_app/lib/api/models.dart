// Data classes mirroring the NewsVista API JSON (see README "API").

DateTime? _date(dynamic v) => v == null ? null : DateTime.tryParse(v as String)?.toLocal();
List<T> _list<T>(dynamic v, T Function(Map<String, dynamic>) f) =>
    (v as List? ?? const []).map((e) => f(e as Map<String, dynamic>)).toList();
List<String> _strings(dynamic v) => (v as List? ?? const []).map((e) => e.toString()).toList();
List<int> _ints(dynamic v) => (v as List? ?? const []).map((e) => (e as num).toInt()).toList();

class StoryListResponse {
  final DateTime? lastSuccessfulCollectionAt;
  final DateTime? servedAt;
  final int total;
  final int windowHours;
  final List<StorySummary> items;

  /// Set when this list came from the offline cache instead of the server.
  final DateTime? cachedAt;
  bool get fromCache => cachedAt != null;

  StoryListResponse.fromJson(Map<String, dynamic> j, {this.cachedAt})
      : lastSuccessfulCollectionAt = _date(j['last_successful_collection_at']),
        servedAt = _date(j['served_at']),
        total = (j['total'] as num?)?.toInt() ?? 0,
        windowHours = (j['window_hours'] as num?)?.toInt() ?? 168,
        items = _list(j['items'], StorySummary.fromJson);
}

class StorySummary {
  final String id;
  final String headline;
  final DateTime? latestPublishedAt;
  final int publisherCount;
  final int articleCount;
  final List<String> publishers;
  final List<String> categories;
  final String summary;
  final String summaryLabel;
  final String? imageUrl;
  final String aiStatus;

  bool get hasAi => aiStatus == 'current' || aiStatus == 'outdated';

  StorySummary.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String,
        headline = j['headline'] as String? ?? '',
        latestPublishedAt = _date(j['latest_published_at']),
        publisherCount = (j['publisher_count'] as num?)?.toInt() ?? 0,
        articleCount = (j['article_count'] as num?)?.toInt() ?? 0,
        publishers = _strings(j['publishers']),
        categories = _strings(j['categories']),
        summary = j['summary'] as String? ?? '',
        summaryLabel = j['summary_label'] as String? ?? 'Publisher excerpt (original wording)',
        imageUrl = j['image_url'] as String?,
        aiStatus = j['ai_status'] as String? ?? 'pending';
}

class StoryDetail {
  final String id;
  final String headline;
  final DateTime? updatedAt;
  final DateTime? latestPublishedAt;
  final int publisherCount;
  final int articleCount;
  final String? imageUrl;
  final Overview overview;
  final List<PublisherCoverage> publishers;
  final Background background;
  final Analysis analysis;
  final DateTime? lastSuccessfulCollectionAt;
  final DateTime? cachedAt;
  bool get fromCache => cachedAt != null;

  StoryDetail.fromJson(Map<String, dynamic> j, {this.cachedAt})
      : id = j['id'] as String,
        headline = j['headline'] as String? ?? '',
        updatedAt = _date(j['updated_at']),
        latestPublishedAt = _date(j['latest_published_at']),
        publisherCount = (j['publisher_count'] as num?)?.toInt() ?? 0,
        articleCount = (j['article_count'] as num?)?.toInt() ?? 0,
        imageUrl = j['image_url'] as String?,
        overview = Overview.fromJson(j['overview'] as Map<String, dynamic>),
        publishers = _list(j['publishers'], PublisherCoverage.fromJson),
        background = Background.fromJson(j['background'] as Map<String, dynamic>),
        analysis = Analysis.fromJson(j['analysis'] as Map<String, dynamic>),
        lastSuccessfulCollectionAt = _date(j['last_successful_collection_at']);
}

class Overview {
  final String kind; // ai_generated | publisher_excerpt
  final String label;
  final String text;
  final DateTime? generatedAt;

  bool get isAi => kind == 'ai_generated';

  Overview.fromJson(Map<String, dynamic> j)
      : kind = j['kind'] as String? ?? 'none',
        label = j['label'] as String? ?? '',
        text = j['text'] as String? ?? '',
        generatedAt = _date(j['generated_at']);
}

class PublisherCoverage {
  final String publisher;
  final List<ArticleRef> articles;

  PublisherCoverage.fromJson(Map<String, dynamic> j)
      : publisher = j['publisher'] as String,
        articles = _list(j['articles'], ArticleRef.fromJson);
}

class ArticleRef {
  final String id;
  final String title;
  final String url;
  final DateTime? publishedAt;
  final String excerpt;
  final String excerptLabel;
  final String? imageUrl;

  ArticleRef.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String,
        title = j['title'] as String? ?? '',
        url = j['url'] as String? ?? '',
        publishedAt = _date(j['published_at']),
        excerpt = j['excerpt'] as String? ?? '',
        excerptLabel = j['excerpt_label'] as String? ?? 'Publisher excerpt',
        imageUrl = j['image_url'] as String?;
}

class Background {
  final String status; // available | none | pending
  final String? message;
  final List<BackgroundLinkItem> links;

  Background.fromJson(Map<String, dynamic> j)
      : status = j['status'] as String? ?? 'none',
        message = j['message'] as String?,
        links = _list(j['links'], BackgroundLinkItem.fromJson);
}

class BackgroundLinkItem {
  final String title;
  final String description;
  final String url;
  final String provider;
  final String? thumbnailUrl;

  BackgroundLinkItem.fromJson(Map<String, dynamic> j)
      : title = j['title'] as String? ?? '',
        description = j['description'] as String? ?? '',
        url = j['url'] as String? ?? '',
        provider = j['provider'] as String? ?? 'Reference',
        thumbnailUrl = j['thumbnail_url'] as String?;
}

class Analysis {
  final String status; // current | outdated | pending | failed | expired_inputs
  final String statusMessage;
  final int? analysisId;
  final int version;
  final DateTime? generatedAt;
  final String? model;
  final AnalysisContent? content;

  bool get hasContent => content != null;

  Analysis.fromJson(Map<String, dynamic> j)
      : status = j['status'] as String? ?? 'pending',
        statusMessage = j['status_message'] as String? ?? '',
        analysisId = (j['analysis_id'] as num?)?.toInt(),
        version = (j['version'] as num?)?.toInt() ?? 0,
        generatedAt = _date(j['generated_at']),
        model = j['model'] as String?,
        content = j['content'] == null ? null : AnalysisContent.fromJson(j['content'] as Map<String, dynamic>);
}

class CitedText {
  final String text;
  final List<int> citations;
  final String? flag;

  CitedText.fromJson(Map<String, dynamic> j)
      : text = j['text'] as String? ?? '',
        citations = _ints(j['citations']),
        flag = j['flag'] as String?;
}

class Perspective {
  final String id;
  final String name;
  final String summary;
  final String caveats;
  final List<CitedText> claims;

  List<int> get citationNumbers => {for (final c in claims) ...c.citations}.toList()..sort();

  Perspective.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String? ?? '',
        name = j['name'] as String? ?? '',
        summary = j['summary'] as String? ?? '',
        caveats = j['caveats'] as String? ?? '',
        claims = _list(j['claims'], CitedText.fromJson);
}

class Citation {
  final int number;
  final String publisher;
  final String title;
  final String url;
  final DateTime? publishedAt;

  Citation.fromJson(Map<String, dynamic> j)
      : number = (j['number'] as num).toInt(),
        publisher = j['publisher'] as String? ?? '',
        title = j['title'] as String? ?? '',
        url = j['url'] as String? ?? '',
        publishedAt = _date(j['published_at']);
}

class AnalysisContent {
  final CitedText overview;
  final List<CitedText> keyPoints;
  final List<CitedText> agreements;
  final List<CitedText> disagreements;
  final List<CitedText> uncertainties;
  final String perspectivesStatus;
  final String? perspectivesMessage;
  final List<Perspective> perspectives;
  final List<String> limitations;
  final String scopeDisclosure;
  final String scopeKind;
  final bool needsReview;
  final List<String> reviewNotes;
  final List<Citation> citations;

  Citation? citation(int n) {
    for (final c in citations) {
      if (c.number == n) return c;
    }
    return null;
  }

  AnalysisContent.fromJson(Map<String, dynamic> j)
      : overview = CitedText.fromJson(j['overview'] as Map<String, dynamic>),
        keyPoints = _list(j['key_points'], CitedText.fromJson),
        agreements = _list(j['agreements'], CitedText.fromJson),
        disagreements = _list(j['disagreements'], CitedText.fromJson),
        uncertainties = _list(j['uncertainties'], CitedText.fromJson),
        perspectivesStatus = j['perspectives_status'] as String? ?? 'insufficient_evidence',
        perspectivesMessage = j['perspectives_message'] as String?,
        perspectives = _list(j['perspectives'], Perspective.fromJson),
        limitations = _strings(j['limitations']),
        scopeDisclosure = (j['input_scope'] as Map<String, dynamic>?)?['disclosure'] as String? ?? '',
        scopeKind = (j['input_scope'] as Map<String, dynamic>?)?['kind'] as String? ?? '',
        needsReview = j['needs_review'] as bool? ?? false,
        reviewNotes = _strings(j['review_notes']),
        citations = _list(j['citations'], Citation.fromJson);
}

/// A source cited by an Ask AI answer: an article, a background page, or a story.
class AskCitation {
  final int number;
  final String kind; // article | background | story
  final String title;
  final String publisher;
  final String? url;
  final String? storyId;
  final DateTime? publishedAt;

  AskCitation.fromJson(Map<String, dynamic> j)
      : number = (j['number'] as num).toInt(),
        kind = j['kind'] as String? ?? 'article',
        title = j['title'] as String? ?? '',
        publisher = j['publisher'] as String? ?? '',
        url = j['url'] as String?,
        storyId = j['story_id'] as String?,
        publishedAt = _date(j['published_at']);
}

/// Server reply to an Ask AI question (generated on the server, never on the phone).
class AskReply {
  final String label;
  final String answer;
  final List<AskCitation> citations;
  final String? generalContext;
  final String generalContextLabel;
  final List<String> followUps;
  final String? flag;
  final String model;
  final bool cached;
  final DateTime? generatedAt;

  AskReply.fromJson(Map<String, dynamic> j)
      : label = j['label'] as String? ?? 'AI-generated',
        answer = j['answer'] as String? ?? '',
        citations = _list(j['citations'], AskCitation.fromJson),
        generalContext = j['general_context'] as String?,
        generalContextLabel = j['general_context_label'] as String? ?? 'General background from the AI model',
        followUps = _strings(j['follow_up_questions']),
        flag = j['flag'] as String?,
        model = j['model'] as String? ?? '',
        cached = j['cached'] as bool? ?? false,
        generatedAt = _date(j['generated_at']);
}

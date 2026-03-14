/**
 * Google Apps Script - Form Creator
 * 
 * Deploy this as a web app to create Google Forms programmatically.
 * 
 * Deployment instructions:
 * 1. Go to https://script.google.com
 * 2. Create a new project
 * 3. Paste this code
 * 4. Click Deploy → New deployment
 * 5. Select type "Web app"
 * 6. Execute as: Me
 * 7. Who has access: Anyone
 * 8. Click Deploy
 * 9. Copy the Web App URL
 * 10. Add it to your .env as APPS_SCRIPT_WEB_APP_URL
 *
 * Optional: Set APPS_SCRIPT_SECRET in Script Properties for shared-secret auth.
 */

/**
 * Set choices with correct-answer feedback on a quiz item.
 *
 * Works with both CheckboxItem and MultipleChoiceItem since they share
 * the same createChoice / setPoints / setFeedback* API surface.
 */
function _setChoicesWithFeedback(item, options, correctAnswer, points, explanation) {
  // Verify correctAnswer is actually in the options list
  var hasCorrect = options.indexOf(correctAnswer) !== -1;
  item.setChoices(options.map(function(opt) {
    return item.createChoice(opt, hasCorrect && opt === correctAnswer);
  }));
  // Only set points when there is a valid correct answer and positive points
  if (hasCorrect && points > 0) {
    item.setPoints(points);
  }
  if (explanation && hasCorrect) {
    item.setFeedbackForCorrect(
      FormApp.createFeedback().setText(explanation).build()
    );
    item.setFeedbackForIncorrect(
      FormApp.createFeedback().setText(explanation).build()
    );
  }
}

function doPost(e) {
  try {
    // Parse the request
    var data = JSON.parse(e.postData.contents);

    // Validate shared secret if configured
    var expectedSecret = PropertiesService.getScriptProperties().getProperty('APPS_SCRIPT_SECRET');
    if (expectedSecret && expectedSecret !== data.secret) {
      return ContentService
        .createTextOutput(JSON.stringify({
          success: false,
          error: 'Unauthorized: invalid secret',
          message: 'Authentication failed'
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    var title = data.title || 'Untitled Form';
    var questions = data.questions || [];
    var items = data.items || [];
    
    // Create the form
    var form = FormApp.create(title);
    form.setIsQuiz(true);

    var itemsById = {};
    for (var j = 0; j < items.length; j++) {
      if (items[j] && items[j].id) {
        itemsById[items[j].id] = items[j];
      }
    }

    // Google Forms title limit (~1600 chars); overflow goes to helpText
    var TITLE_LIMIT = 1500;
    function _safeTitleAndHelp(formItem, text) {
      text = text || '';
      if (text.length <= TITLE_LIMIT) {
        formItem.setTitle(text);
      } else {
        formItem.setTitle(text.substring(0, TITLE_LIMIT) + '…');
        formItem.setHelpText(text);
      }
    }

    function addContextItem(item) {
      if (!item) {
        return;
      }
      try {
      if (item.type === 'section') {
        var pageBreak = form.addPageBreakItem();
        pageBreak.setTitle((item.title || '').substring(0, TITLE_LIMIT));
      } else if (item.type === 'paragraph') {
        var textItem = form.addSectionHeaderItem();
        _safeTitleAndHelp(textItem, item.text || '');
      } else if (item.type === 'table') {
        var tableItem = form.addSectionHeaderItem();
        _safeTitleAndHelp(tableItem, item.text || '');
      } else if (item.type === 'image') {
        var imageItem = form.addImageItem();
        if (item.title) {
          imageItem.setTitle(item.title);
        }
        if (item.image_data && item.image_mime_type) {
          var imgData = Utilities.base64Decode(item.image_data);
          var blob = Utilities.newBlob(imgData, item.image_mime_type, 'doc-image');
          imageItem.setImage(blob);
        } else {
          var imageUrl = item.source_url || item.sourceUrl;
          if (imageUrl) {
            try {
              var image = UrlFetchApp.fetch(imageUrl).getBlob();
              imageItem.setImage(image);
            } catch (imgError) {
              Logger.log('Failed to fetch image: ' + imageUrl + ' - ' + imgError.toString());
              // Skip this image gracefully
            }
          }
        }
      }
      } catch (ctxErr) {
        Logger.log('Skipping context item (type=' + (item.type || 'unknown') + '): ' + ctxErr.toString());
      }
    }

    function addQuestion(q, index) {
      var questionText = (index + '. ') + (q.question || 'Question ' + index);
      var options = q.options || [];
      var required = q.required || false;
      var type = q.type || 'multiple_choice';
      var correctAnswer = q.correct_answer || q.correctAnswer || '';
      var explanation = q.explanation || '';
      var points = q.points || 0;

      try {
      // Deduplicate options (Google Forms rejects duplicate choice values)
      var seen = {};
      var uniqueOptions = [];
      for (var oi = 0; oi < options.length; oi++) {
        var optKey = options[oi];
        if (!seen[optKey]) {
          seen[optKey] = true;
          uniqueOptions.push(optKey);
        }
      }
      options = uniqueOptions;

      if (type === 'checkbox') {
        var checkbox = form.addCheckboxItem();
        checkbox.setTitle(questionText);
        if (options.length) {
          if (correctAnswer) {
            _setChoicesWithFeedback(checkbox, options, correctAnswer, points, explanation);
          } else {
            checkbox.setChoiceValues(options);
          }
        }
        checkbox.setRequired(required);
      } else if (type === 'short_answer') {
        var text = form.addTextItem();
        text.setTitle(questionText);
        text.setRequired(required);
      } else if (type === 'paragraph') {
        var paragraphText = form.addParagraphTextItem();
        paragraphText.setTitle(questionText);
        paragraphText.setRequired(required);
      } else {
        // Default: multiple_choice — must have at least one option
        if (!options.length) {
          var text2 = form.addTextItem();
          text2.setTitle(questionText);
          text2.setRequired(required);
        } else {
          var mc = form.addMultipleChoiceItem();
          mc.setTitle(questionText);
          if (correctAnswer) {
            _setChoicesWithFeedback(mc, options, correctAnswer, points, explanation);
          } else {
            mc.setChoiceValues(options);
          }
          mc.setRequired(required);
        }
      }
      } catch (qErr) {
        Logger.log('Error adding question ' + index + ': ' + qErr.toString());
        // Fallback: add as plain text item so the question isn't lost
        try {
          var fallback = form.addTextItem();
          fallback.setTitle(questionText);
        } catch (ignore) {}
      }
    }

    // Track which context items have already been added to avoid duplicates
    var addedContextIds = {};

    // Build a set of normalized question texts to filter out paragraph items
    // that are just duplicates of question text
    var questionTexts = {};
    for (var qt = 0; qt < questions.length; qt++) {
      var qText = (questions[qt].question || '').replace(/\s+/g, ' ').trim().toLowerCase();
      if (qText) {
        questionTexts[qText] = true;
      }
    }

    // Add context items and questions in order
    for (var i = 0; i < questions.length; i++) {
      var q = questions[i];
      var contextIds = q.context_ids || q.contextIds || [];
      for (var c = 0; c < contextIds.length; c++) {
        var ctxId = contextIds[c];
        // Skip if this context item was already added to the form
        if (addedContextIds[ctxId]) {
          continue;
        }
        // Skip paragraph/section items whose text is just a question's text
        var ctxItem = itemsById[ctxId];
        if (ctxItem && (ctxItem.type === 'paragraph' || ctxItem.type === 'section')) {
          var ctxText = (ctxItem.text || ctxItem.title || '').replace(/\s+/g, ' ').trim().toLowerCase();
          if (ctxText && questionTexts[ctxText]) {
            continue;
          }
        }
        addContextItem(ctxItem);
        addedContextIds[ctxId] = true;
      }
      addQuestion(q, i + 1);
    }
    
    // Get the form URLs
    var formId = form.getId();
    var editUrl = form.getEditUrl();
    var publishedUrl = form.getPublishedUrl();
    
    // Return success response
    return ContentService
      .createTextOutput(JSON.stringify({
        success: true,
        formId: formId,
        formUrl: publishedUrl,
        editUrl: editUrl,
        message: 'Form created successfully'
      }))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    // Return error response
    return ContentService
      .createTextOutput(JSON.stringify({
        success: false,
        error: error.toString(),
        message: 'Failed to create form'
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService
    .createTextOutput(JSON.stringify({
      status: 'Form Creator Web App is running',
      usage: 'Send POST request with {title: string, questions: array}'
    }))
    .setMimeType(ContentService.MimeType.JSON);
}

// Development-only test function (not invoked by the web app)
function _testCreateForm() {
  var testData = {
    title: "Test Quiz from Apps Script",
    questions: [
      {
        question: "What is 2+2?",
        type: "multiple_choice",
        options: ["3", "4", "5", "6"],
        required: true
      },
      {
        question: "Which are colors?",
        type: "checkbox",
        options: ["Red", "Blue", "Cat"],
        required: false
      }
    ]
  };
  
  // Simulate POST request
  var e = {
    postData: {
      contents: JSON.stringify(testData)
    }
  };
  
  var result = doPost(e);
  Logger.log(result.getContent());
}
